## Supported management interface

BiFrost Quick Support is this fork's supported management interface. The legacy
Tauri desktop server-management GUI and its installer have been retired; their
source remains in Git history. The RustDesk client and customer approval prompts
are separate components and remain supported.

# RustDesk Server Program

This is MTG’s maintained fork of `rustdesk/rustdesk-server`. See
[maintenance and verification](MAINTENANCE.md) for branch boundaries, source
patches, security checks, and artifact evidence. Upstream downloads and manuals
below describe the upstream project.

[![Repository validation](https://github.com/MTG-Thomas/rustdesk-server/actions/workflows/repo-validation.yml/badge.svg?branch=master)](https://github.com/MTG-Thomas/rustdesk-server/actions/workflows/repo-validation.yml)

[**Download**](https://github.com/rustdesk/rustdesk-server/releases)

[**Manual**](https://rustdesk.com/docs/en/self-host/)

[**FAQ**](https://github.com/rustdesk/rustdesk/wiki/FAQ)

[**How to migrate OSS to Pro**](https://rustdesk.com/docs/en/self-host/rustdesk-server-pro/installscript/#convert-from-open-source)

Self-host your own RustDesk server, it is free and open source.

## How to build manually

Use Rust 1.90.0 and install the native build prerequisites listed in
`.github/workflows/repo-validation.yml`. Apply the recorded common-library patch
before building; its script rejects modified or incompatible preimages.

```bash
git submodule update --init --recursive
python3 scripts/apply_common_patch.py
cargo +1.90.0 build --locked --release
```

Three executables will be generated in target/release.

- hbbs - RustDesk ID/Rendezvous server
- hbbr - RustDesk relay server
- rustdesk-utils - RustDesk CLI utilities

You can find updated binaries on the [Releases](https://github.com/rustdesk/rustdesk-server/releases) page.

If you want extra features, [RustDesk Server Pro](https://rustdesk.com/pricing.html) might suit you better.

If you want to develop your own server, [rustdesk-server-demo](https://github.com/rustdesk/rustdesk-server-demo) might be a better and simpler start for you than this repo.

## Installation

Please follow this [doc](https://rustdesk.com/docs/en/self-host/rustdesk-server-oss/)
