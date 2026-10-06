# Maintaining the MTG RustDesk fork

`master` is the default source branch. `codex/websocket-registration` maintains
Quick Support's WebSocket transport and image. Changes to one branch do not
qualify the other; each has its own dependency lockfile and common-library patch.

## Local source checks

Initialize recursive submodules, then run these commands with Rust 1.90.0 and
the repository's native build prerequisites installed:

```sh
python3 -m unittest discover -s tests -p test_common_patch.py
python3 -m unittest discover -s tests -p test_sonar_evidence.py
python3 scripts/apply_common_patch.py
cargo +1.90.0 check --locked --workspace
cargo +1.90.0 fmt --all -- --check
cargo +1.90.0 clippy --locked --workspace --all-targets --all-features -- -D warnings
cargo +1.90.0 test --locked --workspace --all-features
```

The native check generates `src/version.rs` for the formatting check. The common
patch deliberately modifies submodule files locally; its manifest records the
exact before/after content. Never commit an unpublished replacement submodule
revision. When updating that revision, regenerate and review the downstream patch
and manifest as described in `patches/hbb-common/README.md`.

## Automated evidence

Repository validation checks Rust formatting, diagnostics, tests, measured
coverage, lockfile and auditable-binary dependencies, and CycloneDX inventories.
An audit build omits debug symbols to stay within the auditor's binary-size limit;
its embedded dependency metadata remains mandatory. Both complete lockfile and
compiled-binary audits run without advisory ignores.

CodeQL covers Rust, Actions, Python, and JavaScript/TypeScript. Authored UI assets
are built before Rust extraction so Tauri macros can resolve their asset paths.
Review extraction diagnostics as well as finding counts: a successful upload with
incomplete extraction does not qualify source analysis.

The Rust Sonar adapter uses actual LCOV and Clippy JSON produced from the exact
candidate head. The consuming job verifies head, base, patch-manifest digest, and
report digests. Fork pull requests receive no scanning credentials. Generated
version/protobuf build output is excluded from the LCOV import; authored server
and common-library source remain covered by analysis.

A new Sonar project is initialized once from original `master` commit
`a7736be5e40f85bfc141120dce587e836e5d4b80`, with its actual tests and coverage.
Existing backlog is report-only; this initialization is not a clean quality-gate
attestation or a merge/deployment candidate. Candidate scans await their own gate.
Before relying on Sonar for admission, verify project/analysis/head/base identity,
actual indexed files and imported coverage, effective exclusions, new-code policy,
small-change behavior, and supported branch/PR analysis. Missing evidence is pending.

Dependabot checks Cargo, Actions, submodules, and the authored npm UI on both
maintained branches. Minor/patch updates are grouped; major updates remain separate
for deliberate review. npm version updates use a seven-day patch/fourteen-day minor
cooldown. Security updates remain eligible immediately.

## Image and delivery boundaries

The maintained branch builds and exercises the patched BusyBox applets, RustDesk
protocol, and S6 lifecycle before registry authentication. Publication inventories
the tested image and attaches build provenance and its SPDX SBOM to that image's
immutable digest. Confirm registry attestations after publication; workflow source
alone is not evidence that an attestation exists.

The default branch has no Quick Support image; its image-check disposition is
explicitly inapplicable. A merged source change or published image does not prove
an ACA deployment or Windows customer/technician acceptance. Those have separate
authorization and runtime verification requirements.

## Visible dependency debt

RustSec warnings for legacy unmaintained crates remain visible, including
`sodiumoxide`, `dlopen_derive`, `ansi_term`, and `atty`; the default branch also
retains `bincode` 1.x. The `atty` unsoundness advisory concerns its Windows code.
These warnings are not vulnerability-free or cross-platform compatibility claims.
Replacing cryptographic or serialized formats requires explicit compatibility
work and tests; do not suppress advisories to make that work disappear.
