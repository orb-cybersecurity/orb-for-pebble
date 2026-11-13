#!/usr/bin/env python3
"""Follow Core's releases.

Usage:
    python3 tools/upstream.py status       compare the pinned tag with Core's newest tag;
                                           exits 3 if a newer one exists
    python3 tools/upstream.py bump <tag>   pin <tag>, set version.properties to <tag>-orb1,
                                           and report what the overlay needs looked at

Core marks releases only with tags like 1.18.0.1 on its repository, so tags are what this reads.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "mobileapp"
UPSTREAM = "https://github.com/coredevices/mobileapp.git"
TAG = re.compile(r"\d+(?:\.\d+){2,3}")
NEWER_EXISTS = 3

sys.path.insert(0, str(ROOT))
import apply  # noqa: E402


def git(*args: str, cwd: Path = APP) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def tag_key(tag: str) -> tuple[int, ...]:
    return tuple(int(p) for p in tag.split("."))


def upstream_tags() -> list[str]:
    refs = git("ls-remote", "--tags", "--refs", UPSTREAM, cwd=ROOT).splitlines()
    tags = (line.split("refs/tags/", 1)[1] for line in refs)
    return sorted((t for t in tags if TAG.fullmatch(t)), key=tag_key)


def pinned_tag() -> str:
    return apply.read_version()[0].split("-orb")[0]


def version_code(tag: str, orb_release: int) -> int:
    parts = tag_key(tag)
    upstream = sum(scale * part for scale, part in zip((10_000_000, 100_000, 1_000, 1), parts))
    return upstream * 10 + orb_release


def status() -> int:
    pinned, latest = pinned_tag(), upstream_tags()[-1]
    if tag_key(latest) > tag_key(pinned):
        print(f"Core has released {latest}; Orb is pinned to {pinned}.")
        return NEWER_EXISTS
    print(f"Orb is pinned to Core's newest tag, {pinned}.")
    return 0


def bump(tag: str) -> int:
    if not TAG.fullmatch(tag):
        print(f"{tag!r} does not look like one of Core's release tags", file=sys.stderr)
        return 2
    old = pinned_tag()
    git("fetch", "--quiet", "origin", "tag", tag)
    git("checkout", "--quiet", "--force", tag)
    git("clean", "-fdq")
    (ROOT / "version.properties").write_text(
        f"versionName={tag}-orb1\nversionCode={version_code(tag, 1)}\n"
    )
    print(f"Pinned {tag} (was {old}); version {tag}-orb1.")

    stale = [
        path for path, digest in apply.REPLACED.items()
        if not (APP / path).is_file() or apply.sha256(APP / path) != digest
    ]
    if stale:
        print("\nCore changed files the overlay replaces. Port each change into the overlay copy,")
        print("then put the new hash in REPLACED in apply.py:")
        for path in stale:
            new = apply.sha256(APP / path) if (APP / path).is_file() else "(deleted upstream)"
            print(f"  {path}\n    new sha256: {new}\n    upstream diff: git -C mobileapp diff {old} {tag} -- {path}")
    else:
        print("Files the overlay replaces are unchanged upstream.")

    result = subprocess.run([sys.executable, str(ROOT / "apply.py")], capture_output=True, text=True)
    if result.returncode != 0:
        print("\napply.py does not apply cleanly yet:\n" + result.stderr.strip())
    else:
        print("\napply.py applies cleanly. Build, run tools/check_apk.py, and test before committing.")
    # Leave the checkout pristine at the new tag, as apply.py expects.
    git("checkout", "--quiet", "--force", "HEAD")
    git("clean", "-fdq")
    return 0 if not stale and result.returncode == 0 else 1


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "status":
        return status()
    if len(sys.argv) == 3 and sys.argv[1] == "bump":
        return bump(sys.argv[2])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
