#!/usr/bin/env python3
"""Require embedded dependency metadata; never accept panic-string fallback."""

import re
import subprocess
import sys

SUPPORTED = {f"target/{profile}/{name}" for profile in ("debug", "release") for name in ("hbbs", "hbbr", "rustdesk-utils")}

for argument in sys.argv[1:]:
    if argument not in SUPPORTED:
        raise SystemExit("Unsupported audit artifact path")
    binary = next(path for path in SUPPORTED if path == argument)
    sections = subprocess.check_output(["readelf", "--wide", "--section-headers", "--", binary], text=True)
    if not re.search(r"\s\.dep-v0\s", sections):
        raise SystemExit(f"Complete auditable dependency metadata missing: {binary}")
    print(f"Embedded dependency metadata present: {binary}")
if len(sys.argv) < 2:
    raise SystemExit("At least one ELF binary is required")
