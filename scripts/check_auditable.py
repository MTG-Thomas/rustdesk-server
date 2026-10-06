#!/usr/bin/env python3
"""Require embedded dependency metadata; never accept panic-string fallback."""

import subprocess
import sys

for binary in sys.argv[1:]:
    sections = subprocess.check_output(["readelf", "--section-headers", binary], text=True)
    if ".dep-v0" not in sections:
        raise SystemExit(f"Complete auditable dependency metadata missing: {binary}")
    print(f"Embedded dependency metadata present: {binary}")
if len(sys.argv) < 2:
    raise SystemExit("At least one ELF binary is required")
