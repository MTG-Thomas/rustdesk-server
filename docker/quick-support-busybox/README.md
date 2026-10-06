# BusyBox security replacement

The Quick Support S6 runtime inherits an unpatched BusyBox 1.36.1 binary.
Replace `/bin/busybox` and convert every original BusyBox hardlink alias to a
symlink to that binary before replacement. Upstream puts even `sh`, `wget` and
`tar` at separate hardlink paths; overwriting one inode alone leaves them old.
Preserve unrelated executables, S6 overlay,
RustDesk source/lockfile and daemon configuration.

BusyBox 1.37.0 source comes from https://busybox.net/downloads/busybox-1.37.0.tar.bz2,
verified against the publisher's SHA-256
`3311dff32e746499f4df0d5df04d7eb396382d7e108bb9250e7b519b837043a4`.
It is compiled statically against musl using the pinned existing Alpine builder.
The upstream `defconfig`, with `CONFIG_STATIC=y`, supplies the applets used by S6.
`CONFIG_TC` is disabled: its obsolete CBQ structures were removed from current
Linux headers, and this ACA server does not use the traffic-control applet.

- CVE-2022-48174: 1.37.0 includes upstream commit
  https://github.com/mirror/busybox/commit/d417193cf37ca1005830d7e16f5fa7e1d8a44209.
  The advisory's "before 1.35" wording does not establish that 1.36.1 is fixed;
  the deployed binary reproduces the `${0::0/0~09J}` crash.
- CVE-2025-46394: backport upstream commit
  https://github.com/mirror/busybox/commit/f5e1bf966b19ea1821f00a8c9ecd7774598689b4.
  Include the missing verbose filename hunk from Debian maintainer Michael
  Tokarev, https://lists.busybox.net/pipermail/busybox/2026-February/091910.html
  (Debian source `1:1.37.0-8`, patch `CVE-2025-46394-2.patch`). Both normal and
  verbose tar listings sanitize names and link targets.
- CVE-2025-60876: use the small maintainer-submitted patch at
  https://lists.busybox.net/pipermail/busybox/2025-November/091818.html.
  Reject raw C0 controls and spaces before sending a request. Percent-encoded
  paths remain usable. This is a backport, not a claim that vanilla 1.37.0 fixes it.

`tests/busybox_security.py` exercises the actual compiled binary: malformed ash
arithmetic, tar filenames/link targets, every non-NUL C0 byte and raw space in
wget URLs, and an ordinary percent-encoded HTTP request. All network tests are
loopback-only. The image build must pass these checks before publication.

Complete corresponding source is retained in the final image at
`/usr/share/licenses/busybox/`: the upstream tarball, LICENSE, all three patches and
exact generated `build.config`. Rebuild steps are in `Dockerfile.quick-support`.
BusyBox remains GPL-2.0-only; RustDesk remains AGPL-3.0-only. Version-only
scanners may continue reporting backported CVEs; retain patch and runtime
regression evidence rather than dismissing alerts without a rescan.
