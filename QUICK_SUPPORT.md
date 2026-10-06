# Quick Support WebSocket fork

This downstream AGPL-3.0 fork starts from RustDesk OSS server 1.1.16,
commit `73523b31cfd25d77dee862e6fc9f5e1fb5e485ef`, with its original
`hbb_common` submodule and Cargo lockfile. Bifrost remains a separate program.

The scoped change adds controlled-client registration and server-driven
heartbeats to the existing WebSocket rendezvous listener. It preserves UUID,
key, IP and registration-rate checks through a shared registration method;
serializes concurrent registration; uses bounded outgoing routes; and fences
cleanup so a replaced connection cannot expire its replacement. Multiple
clients behind one proxy retain separate transport addresses. Forwarded
headers are not trusted as connection identity. Online queries work over the
same listener. Native UDP registration remains supported; native TCP
controlled-client registration is outside this patch.

WebSocket registration uses one endpoint ID per stream, maximum 64-byte IDs,
256-byte UUIDs, 32-byte public keys, 64 KiB frames/messages, and a 32-message
outgoing queue. Heartbeats are empty binary frames at 15-second intervals;
clients acknowledge with empty binary frames. Missing acknowledgements close
registration after 45 seconds. The existing 30-second peer lease determines
online status between acknowledgements. Disconnect marks the owning endpoint
offline immediately. Endpoint UUID/key checks are inherited OSS behavior,
not proof of the assigned technician's identity.

This is a disposable transport spike. It does not implement Bifrost grants,
customer consent, Windows isolation, elevation telemetry or launcher cleanup.
Those acceptance gates remain separate. TLS terminates at the ACA HTTPS
boundary; client-to-client RustDesk encryption remains independent. Production
capacity, proxy IP rate-limit aggregation and peer re-registration after replica
replacement require further evaluation.

## Build and verification

`Dockerfile.quick-support` pins Rust 1.90.0/Alpine and the official 1.1.16 S6
runtime by Linux amd64 digest. The inherited BusyBox is replaced by a static
musl BusyBox 1.37.0 build: its ash includes upstream fix
`d417193cf37ca1005830d7e16f5fa7e1d8a44209` (CVE-2022-48174), and the image
backports the tar output sanitization and wget URL validation patches described
in `docker/quick-support-busybox/README.md`. Cargo resolves only the existing lockfile. The
published image retains the upstream license and points back to this repository.
The Quick Support image workflow builds binaries, runs real protocol tests,
and publishes to GHCR only after those tests pass. Deployment consumes its
immutable digest; node-local builds are never a deployment source.

The protocol tests start an isolated hbbs with a temporary DB/key and test real
UDP/WebSocket messages, request/response routing, conflicting UUIDs, multiple
proxy clients, reconnect ownership, malformed keys, ID changes, heartbeat
acknowledgements, expiry and disconnect. They require `websockets==15.0.1`:

```sh
cargo build --locked --bins
python tests/run_protocol_tests.py target/debug/hbbs
```

For a published image, expose native ports only within a disposable local test
network. ACA exposes HTTPS with `/ws/id` forwarded to 21118 and `/ws/relay`
to 21119, one replica. Keep the server private key in Key Vault. Public image
source is available at https://github.com/MTG-Thomas/rustdesk-server; deployed
source offers must identify the exact image revision.
