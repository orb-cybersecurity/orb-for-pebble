#!/usr/bin/env python3
"""Fail if an APK contains, or refers to, code Orb for Pebble must not ship.

Usage: python3 tools/check_apk.py path/to/app.apk

Reads the class names straight from the APK's dex files, and the manifest and the resources it
names through aapt2, so the result describes the artifact and not the build scripts: a library
merged into the manifest can't change what Orb backs up or let plain HTTP back in unnoticed.

aapt2 is taken from $AAPT2, else from the newest build-tools in $ANDROID_HOME (default
~/Android/Sdk).
"""

import os
import json
import re
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

FORBIDDEN_CLASSES = {
    "Lcom/google/firebase/": "Firebase SDK",
    "Lcom/google/android/gms/": "Google Play services",
    "Lcom/google/android/play/": "Google Play Core",
    "Lcom/google/android/libraries/identity/": "Google identity",
    "Lcom/google/android/datatransport/": "Google data transport",
    "Lcom/crashlytics/": "Crashlytics",
    "Lcom/mixpanel/": "Mixpanel",
    "Lcom/wtlp/": "Index 01 radio library (binary only)",
}

FORBIDDEN_LIBRARIES = {
    "libcactus_engine.so": "Cactus engine (binary only)",
    "libhaversinesatellitelibrary.so": "Index 01 radio library (binary only)",
    "libppcommon.so": "Index 01 radio library (binary only)",
    "libcrashlytics": "Crashlytics NDK",
}


def uleb128(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, pos
        shift += 7


def dex_classes(data: bytes) -> tuple[set[str], set[str]]:
    """Return (classes defined in this dex, every type descriptor it mentions)."""
    if data[:4] != b"dex\n":
        raise ValueError("not a dex file")
    string_count, string_off, type_count, type_off = struct.unpack_from("<IIII", data, 0x38)
    class_count, class_off = struct.unpack_from("<II", data, 0x60)

    def string(index: int) -> str:
        (offset,) = struct.unpack_from("<I", data, string_off + 4 * index)
        _, start = uleb128(data, offset)
        return data[start:data.index(b"\x00", start)].decode("utf-8", "replace")

    types = [string(struct.unpack_from("<I", data, type_off + 4 * i)[0]) for i in range(type_count)]
    defined = {
        types[struct.unpack_from("<I", data, class_off + 32 * i)[0]] for i in range(class_count)
    }
    return defined, set(types)


# What Android's backup must copy for a restored phone to have Orb as it was (see
# overlay/androidApp/src/main/res/xml/data_extraction_rules.xml), and nothing else.
BACKUP_INCLUDES = {("database", "."), ("sharedpref", "."), ("file", "pbw/")}


def aapt2() -> str:
    if os.environ.get("AAPT2"):
        return os.environ["AAPT2"]
    sdk = Path(os.environ.get("ANDROID_HOME", Path.home() / "Android" / "Sdk"))
    tools = sorted(sdk.glob("build-tools/*/aapt2"), key=lambda p: [int(n) if n.isdigit() else n for n in re.split(r"[.-]", p.parent.name)])
    if not tools:
        raise SystemExit(f"check_apk: no aapt2 under {sdk}; set AAPT2 or ANDROID_HOME")
    return str(tools[-1])


class Node:
    def __init__(self, tag: str):
        self.tag, self.attrs, self.children = tag, {}, []

    def find(self, tag: str) -> list["Node"]:
        found = [c for c in self.children if c.tag == tag]
        for child in self.children:
            found += child.find(tag)
        return found


ATTR = re.compile(r'^A: (?:\S+:)?(\w+)(?:\(0x[0-9a-f]+\))?=(?:"((?:[^"\\]|\\.)*)"|(\S+))')


def xmltree(apk: str, path: str) -> Node:
    """Parse `aapt2 dump xmltree` output into a tree of elements and their attributes."""
    out = subprocess.run([aapt2(), "dump", "xmltree", "--file", path, apk],
                         check=True, capture_output=True, text=True).stdout
    root, stack = Node("#document"), []
    for line in out.splitlines():
        depth = len(line) - len(line.lstrip())
        text = line.strip()
        if text.startswith("E: "):
            node = Node(text[3:].split(" ")[0])
            while stack and stack[-1][0] >= depth:
                stack.pop()
            (stack[-1][1] if stack else root).children.append(node)
            stack.append((depth, node))
        elif text.startswith("A: ") and stack:
            m = ATTR.match(text)
            if m:
                stack[-1][1].attrs[m.group(1)] = m.group(2) if m.group(2) is not None else m.group(3)
    return root


def resource_files(apk: str) -> dict[str, tuple[str, str]]:
    """Resource ID (0x7f...) -> (type/name, file in the APK), for file resources."""
    out = subprocess.run([aapt2(), "dump", "resources", apk], check=True, capture_output=True, text=True).stdout
    files, current = {}, None
    for line in out.splitlines():
        m = re.match(r"\s*resource (0x[0-9a-f]+) (\S+)", line)
        if m:
            current = m.groups()
            continue
        m = re.match(r"\s*\(\) \(file\) (\S+)", line)
        if m and current:
            files[current[0]] = (current[1], m.group(1))
    return files


def exported_components(manifest: Node, application: Node, resource_names: dict[str, str]) -> list[dict[str, str]]:
    """Release surface, including disabled aliases and system-bound services."""
    actual = []
    app_permission = application.attrs.get("permission", "")
    for kind in ("activity", "activity-alias", "service", "receiver", "provider"):
        for component in manifest.find(kind):
            attrs = component.attrs
            exported = attrs.get("exported", "true" if kind != "provider" and component.find("intent-filter") else "false")
            if exported != "true":
                continue
            inherited = app_permission
            if kind == "activity-alias":
                target = attrs.get("targetActivity")
                inherited = next((n.attrs.get("permission", app_permission) for n in manifest.find("activity")
                                  if n.attrs.get("name") == target), app_permission)
            permission = attrs.get("permission", inherited)
            enabled = attrs.get("enabled", "true")
            if enabled.startswith("@"):
                enabled = "@" + resource_names.get(enabled.lstrip("@"), "unknown-resource")
            row = dict(kind=kind, name=attrs.get("name", ""), permission=permission,
                       readPermission=attrs.get("readPermission", permission),
                       writePermission=attrs.get("writePermission", permission), enabled=enabled)
            if kind == "activity-alias":
                row["targetActivity"] = attrs.get("targetActivity", "")
            if kind == "provider":
                row["authorities"] = attrs.get("authorities", "")
            actual.append(row)
    return actual


def check_exported_components(manifest: Node, application: Node, resource_names: dict[str, str]) -> list[str]:
    allowed = json.loads((Path(__file__).with_name("exported_components.json")).read_text())
    actual = exported_components(manifest, application, resource_names)
    problems = []
    for component in actual:
        if component not in allowed:
            problems.append("unexpected exported component or permissions: " + json.dumps(component, sort_keys=True))
    for component in allowed:
        if component not in actual:
            problems.append("missing or changed exported component: " + component["name"])
    return problems


def check_activity_classes(manifest: Node, defined: set[str]) -> list[str]:
    """Preview tooling never ships, and every exported activity must be instantiable."""
    problems = []
    package = manifest.find("manifest")[0].attrs.get("package", "")

    def classname(name: str) -> str:
        if name.startswith("."):
            return package + name
        return name if "." in name else package + "." + name

    for kind in ("activity", "activity-alias"):
        for activity in manifest.find(kind):
            name = classname(activity.attrs.get("name", ""))
            target = classname(activity.attrs.get("targetActivity", "")) if kind == "activity-alias" else name
            if any("tooling" in n.lower() or "preview" in n.lower() for n in (name, target)):
                problems.append(f"tooling/preview activity in release manifest: {name}")
            exported = activity.attrs.get("exported", "true" if activity.find("intent-filter") else "false")
            if exported == "true" and "L" + target.replace(".", "/") + ";" not in defined:
                problems.append(f"exported activity class absent from dex: {target}")
    return problems


def check_manifest(apk: str, defined: set[str]) -> list[str]:
    problems = []
    manifest = xmltree(apk, "AndroidManifest.xml")
    application = manifest.find("application")[0]
    files = resource_files(apk)
    resource_dump = subprocess.run([aapt2(), "dump", "resources", apk], check=True,
                                   capture_output=True, text=True).stdout
    resource_names = dict(re.findall(r"^\s*resource (0x[0-9a-f]+) (\S+)", resource_dump, re.MULTILINE))
    problems += check_exported_components(manifest, application, resource_names)
    problems += check_activity_classes(manifest, defined)

    def rules(attr: str, name: str) -> Node | None:
        ref = application.attrs.get(attr, "").lstrip("@")
        resource, path = files.get(ref, (None, None))
        if resource != name:
            problems.append(f"manifest {attr} is {resource or 'unset'}, not Orb's {name}")
            return None
        return xmltree(apk, path)

    if application.attrs.get("allowBackup") != "true":
        problems.append("backup is not allowed: a restore can't bring Orb's data back")
    if application.attrs.get("usesCleartextTraffic") not in (None, "false"):
        problems.append("the manifest allows plain HTTP (usesCleartextTraffic)")

    extraction = rules("dataExtractionRules", "xml/data_extraction_rules")
    if extraction:
        for kind in ("cloud-backup", "device-transfer"):
            sections = extraction.find(kind)
            if len(sections) != 1:
                problems.append(f"data extraction rules have {len(sections)} <{kind}> sections")
                continue
            got = {(n.attrs.get("domain"), n.attrs.get("path")) for n in sections[0].find("include")}
            if got != BACKUP_INCLUDES or sections[0].find("exclude"):
                problems.append(f"<{kind}> copies {sorted(got)}, expected {sorted(BACKUP_INCLUDES)}")
        cloud = extraction.find("cloud-backup")
        if cloud and cloud[0].attrs.get("disableIfNoEncryptionCapabilities") != "true":
            problems.append("cloud backup is not limited to services that encrypt on the phone")
    full = rules("fullBackupContent", "xml/backup_rules")
    if full:
        includes = full.find("include")
        got = {(n.attrs.get("domain"), n.attrs.get("path")) for n in includes}
        if got != BACKUP_INCLUDES or full.find("exclude"):
            problems.append(f"backup rules copy {sorted(got)}, expected {sorted(BACKUP_INCLUDES)}")
        if any("clientSideEncryption" not in n.attrs.get("requireFlags", "") for n in includes):
            problems.append("backup rules copy data without requiring client-side encryption")

    network = rules("networkSecurityConfig", "xml/network_security_config")
    if network:
        for config in network.find("base-config") + network.find("domain-config"):
            if config.attrs.get("cleartextTrafficPermitted") not in (None, "false"):
                problems.append(f"the network security config allows plain HTTP in <{config.tag}>")

        anchors = network.find("certificates")
        if not anchors or any(n.attrs.get("src") != "system" for n in anchors):
            problems.append("network trust anchors must be system CAs only")

    for component in manifest.find("receiver") + manifest.find("activity") + manifest.find("service"):
        if component.attrs.get("name", "").startswith("coredevices.coreapp.debug."):
            problems.append(f"debug component {component.attrs['name']} is in the manifest")
    return problems


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    defined: set[str] = set()
    mentioned: set[str] = set()
    problems: list[str] = []
    with zipfile.ZipFile(sys.argv[1]) as apk:
        names = apk.namelist()
        for name in names:
            if name.startswith("classes") and name.endswith(".dex"):
                d, m = dex_classes(apk.read(name))
                defined |= d
                mentioned |= m
        for name in names:
            for needle, what in FORBIDDEN_LIBRARIES.items():
                if name.startswith("lib/") and needle in name:
                    problems.append(f"native library {name}: {what}")

    for prefix, what in FORBIDDEN_CLASSES.items():
        shipped = sorted(c for c in defined if c.startswith(prefix))
        referenced = sorted(c for c in mentioned - defined if c.startswith(prefix))
        if shipped:
            problems.append(f"{len(shipped)} classes of {what}, e.g. {shipped[0]}")
        if referenced:
            problems.append(f"{len(referenced)} references to missing {what} classes, e.g. {referenced[0]}")

    problems += check_manifest(sys.argv[1], defined)

    print(f"{sys.argv[1]}: {len(defined)} classes in {sum(n.endswith('.dex') for n in names)} dex files")
    if problems:
        print("FAIL")
        for problem in problems:
            print("  " + problem)
        return 1
    print("OK: no forbidden classes or native libraries; backup rules, HTTPS-only and manifest as expected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
