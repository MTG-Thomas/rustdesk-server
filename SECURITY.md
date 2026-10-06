# Security policy

This fork maintains the Quick Support server transport. Upstream RustDesk
desktop clients and unrelated server releases are separate components.

Report vulnerabilities privately through
[GitHub private vulnerability reporting](https://github.com/MTG-Thomas/rustdesk-server/security/advisories/new).
Include the affected commit or image digest, configuration, and a reproducible
example. Never include private server keys, customer identifiers, or credentials.

The maintained Quick Support branch is `codex/websocket-registration`; `master`
tracks the upstream server baseline. A source merge does not deploy an image.
Only artifacts that pass the branch's security, protocol, and runtime checks
are eligible for deployment. Pin production images by digest.

Dependency findings are investigated against the actual resolved build graph.
Unmaintained dependencies remain visible debt; no vulnerability is dismissed
because an upstream release is old or a workflow reports zero findings.
