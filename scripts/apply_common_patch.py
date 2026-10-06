#!/usr/bin/env python3
"""Apply the public downstream changes only to their exact upstream preimage."""

import hashlib
import json
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    directory = root / "patches/hbb-common"
    manifest = json.loads((directory / "manifest.json").read_text())
    patch = directory / "maintenance.patch"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest["patch_sha256"]:
        raise SystemExit("Downstream patch digest mismatch")
    common = root / "libs/hbb_common"
    hashes = {
        name: hashlib.sha256((common / name).read_bytes()).hexdigest()
        for name in manifest["files"]
    }
    if all(hashes[name] == entry["after"] for name, entry in manifest["files"].items()):
        print("Downstream common patch already applied")
        return
    if not all(hashes[name] == entry["before"] for name, entry in manifest["files"].items()):
        raise SystemExit("Common source differs from the recorded upstream preimage")
    command = ["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-d", str(common), "-i", str(patch)]
    subprocess.run(command + ["--dry-run"], check=True)
    subprocess.run(command, check=True)
    if not all(
        hashlib.sha256((common / name).read_bytes()).hexdigest() == entry["after"]
        for name, entry in manifest["files"].items()
    ):
        raise SystemExit("Patched common source digest mismatch")


if __name__ == "__main__":
    main()
