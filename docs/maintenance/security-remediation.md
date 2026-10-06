# CodeQL and RustSec remediation

## Runtime changes

`rustdesk-utils genkeypair [private-key-file]` writes the private key to a new
file (default `id_ed25519`) instead of stdout. It rejects existing files and
symlinks. Unix files are created with mode 0600; Windows inherits the destination
directory ACL, so use a directory restricted to the server administrator.
Only the public key is printed. Peer registration and relay logs no longer dump
registration UUIDs or public-key payloads.

The common library uses `libsodium-rs` 0.2.5 with its pinned
`libsodium-sys-stable` dependency. The image builds the signature-verified native
source bundled in that checksum-locked crate rather than selecting a system
library through `SODIUM_LIB_DIR`. No `fetch-latest` feature is enabled. Existing
Ed25519 key files, signatures and XSalsa20-Poly1305 encrypted frames keep their
formats. Regression tests include RFC 8032 TEST 1 and ciphertext generated
independently with the previous libsodium 1.0.20 C library.

Clap 4 and the existing maintained common-library logger replace the server's
Clap 2/logger dependency paths to `ansi_term` and `atty`. `machine-uid` 0.6
removes the old build-time bindgen path; the Linux machine-ID locations and
returned identity are unchanged. The unused `dlopen` dependency and re-export
are removed from this server-only common patch. The retired desktop GUI is not
a supported consumer of this downstream library.

RustSec checks reject informational warnings as well as vulnerabilities. There
are no advisory ignores or platform filters. The lockfile check includes
optional dependencies; auditable-binary checks inspect the deployed programs.

## CodeQL test-fixture dispositions

The default-branch scan at commit
`043133c3d759265650db8c2dfd6eb7f26e524ad9` reported 66
`rust/hard-coded-cryptographic-value` findings in
`libs/hbb_common/src/config.rs` and
`libs/hbb_common/src/config/permanent_password.rs`.
Each reported location was checked against the exact upstream source plus its
checksum-verified downstream patch. All locations are in the files' final
`#[cfg(test)] mod tests` modules. These values are public, deterministic inputs
to password compatibility tests, not deployed credentials or production keys.
They retain their regression value; the corresponding alerts are dispositioned
individually as false positives with this rationale. Production findings are
fixed in source. Test files remain included in CodeQL scans.

## Default-branch transport changes

HTTPS proxy and secure WebSocket connections never retry with certificate
validation disabled. Switching between Rustls and native TLS retains certificate
and hostname validation; explicit bypass requests fail. Private proxy CAs must
be installed in the trusted system certificate store. Trusted platform-verifier
fallback remains available on mobile targets. Logs no longer include native
certificate-loading error details or home-directory paths.

Optional WebRTC is updated from 0.14 to 0.17, whose upstream DTLS implementation
replaced the unmaintained `bincode` serialization dependency. The real local
WebRTC negotiation/data-channel tests remain part of all-feature verification.
