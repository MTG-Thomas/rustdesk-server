# Downstream common-library patch

The submodule remains pinned to the upstream commit recorded in `manifest.json`.
The public patch contains the downstream TLS dependency update, Rust diagnostics
fixes, and approved formatting cleanup. Its source remains under the upstream
license. This avoids publishing an unreachable submodule commit.

Run `python3 scripts/apply_common_patch.py` after recursive submodule checkout
and before Cargo commands. The helper checks SHA-256 hashes of every touched
file and the patch, dry-runs with zero fuzz, applies it, and checks the result.
It accepts an already patched tree only when every output hash matches.
Any mixed or changed preimage fails rather than overwriting local work.

When upgrading the submodule, review and regenerate this patch against the new
revision. Do not change the gitlink without replacing and verifying the manifest.
