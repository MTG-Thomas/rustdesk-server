#!/usr/bin/env python3
"""Require embedded dependency metadata; never accept panic-string fallback."""

import re
import subprocess
import sys

for binary in sys.argv[1:]:
    sections = subprocess.check_output(["readelf", "--wide", "--section-headers", binary], text=True)
    if not re.search(r"\s\.dep-v0\s", sections):
        raise SystemExit(f"Complete auditable dependency metadata missing: {binary}")
    print(f"Embedded dependency metadata present: {binary}")
if len(sys.argv) < 2:
    raise SystemExit("At least one ELF binary is required")
