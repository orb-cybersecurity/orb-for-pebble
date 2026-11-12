#!/usr/bin/env python3
"""Fail if an APK contains, or refers to, code Orb for Pebble must not ship.

Usage: python3 tools/check_apk.py path/to/app.apk

Reads the class names straight from the APK's dex files, so the result describes the artifact
and not the build scripts.
"""

import struct
import sys
import zipfile

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

    print(f"{sys.argv[1]}: {len(defined)} classes in {sum(n.endswith('.dex') for n in names)} dex files")
    if problems:
        print("FAIL")
        for problem in problems:
            print("  " + problem)
        return 1
    print("OK: no forbidden classes or native libraries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
