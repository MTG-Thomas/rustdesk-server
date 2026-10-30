# ACA transport lifecycle contract v1

Package: RustDesk maintained 1.1.16 lineage, base
`59218fd` on `codex/websocket-registration`. Engineering flow and PR stewardship
procedures: 2026-10-26.1. This source does not qualify master or an ACA image.

`scripts/transport_lifecycle.py` is an executable reference policy seam for the
workspace-next transport adapter, not a deployed HTTP endpoint or Azure scaler.
The authoritative external Cloudflare session service owns persistence, locking,
authentication, trusted receiver grants and request authorization. Instantiate
`Transport` from durable state and atomically serialize every operation per
endpoint, including the final scale decision. An in-memory instance in each API
worker is unsafe. Never accept probe booleans or cleanup assertions from a browser.
No receipt grants customer invitation, connection, elevation, consent or UAC.

## Adapter mapping

Suggested authenticated internal routes (not installed by this PR):

| Route | Policy operation | Required evidence/action |
| --- | --- | --- |
| POST /transport/v1/prepare | prepare | Bind authoritative session/lease and expiry; request protected infra wake workflow |
| POST /transport/v1/readiness | readiness | Fresh same-generation TLS-valid hbbs registration acknowledgement and hbbr synthetic bidirectional relay probe, pinned public-key fingerprint |
| POST /transport/v1/revoke | revoke | Authority revokes receiver grant; disconnect/drain transport separately |
| POST /transport/v1/cleanup | accept_cleanup | Trusted cleanup acceptance after revoke for the same generation |
| POST /transport/v1/drain | drain | Reject new prepares, revoke and accept cleanup for every retained lease before protected scale-to-zero workflow |

Every receipt contains `contract=rustdesk.transport.v1`, `session_id`, `lease_id`,
`generation`, `state`, `reasons` and `action`. Identifiers must be opaque nonsecret
IDs. A blocked receipt's `action` describes the requested outcome, never permission
to execute it. `wake_required` remains blocked pending protocol probes; a prepare
retry with an identical binding is idempotent. Renewal needs an explicit new lease;
revoked IDs cannot be resurrected. `safe_to_zero` is an instant policy decision,
not proof ACA was scaled down: keep the endpoint lock/drain fence through workflow
completion and verify readback. Never remove leases merely because they expired.
Restart increases generation, preserves the pinned public key fingerprint and
invalidates cleanup evidence. The adapter must discard all cached probe evidence
on restart and after revocation; readiness calls must run fresh probes. A drained
instance remains fenced; reopening requires a new generation and authoritative
reconciliation rather than constructing an empty lease list.

The existing `healthcheck.sh` checks S6 processes and is insufficient for this
contract. Reuse the maintained registration tests and infra WSS probe for protocol
evidence, with unique synthetic IDs, wrong-key rejection and no customer session.
Those probes must be scoped to the approved endpoint; freshness, bounded deadlines,
key matching, generation binding and authenticated cleanup remain adapter duties.

## Evidence and remaining blockers (2026-10-30)

Canonical infra source found at `MTG-Thomas/bifrost-infra`,
`bicep/environments/quick-support-spike/aca-server.bicep`, with historical evidence
in `docs/runbooks/quick-support-spike.md`. The inspected local source pins RustDesk
image digest `sha256:4258af2375ff165fd7e096db82a66edabe5accade8ec238394d4d197e926feba`.
Historical evidence records min/max replicas 1, stable Key Vault key, ephemeral
peer registrations and successful long WSS tests; it explicitly leaves zero-scale
and Windows acceptance unqualified. Local infra source is not current runtime proof.

Read-only `az-mi containerapp show` for subscription
`a1d63b24-1202-4bfa-9086-cf32d1d352fc`, group
`rg-mtg-quick-support-spike-eastus2`, app `ca-mtg-quick-support-spike` failed with
`AuthorizationFailed` for `Microsoft.App/containerApps/read`. No personal login,
Azure writes, paid resources, Access changes or Windows actions were performed.
A reviewed task-specific read grant is required to inspect current ACA state.

Passed: `python3 -m unittest discover -s tests -p 'test_*.py'` (30 tests).
The new tests exercise prepare/wake receipts, both-protocol readiness, overlapping
leases, idle protection, revoke/cleanup before zero, binding/replay rejection,
and restart/key continuity at the policy seam. They do not test actual sockets,
Azure wake/zero, key persistence, reconnection or customer cleanup.

Deferred: protected OIDC workflow adapter and durable authority integration,
live wake/probes/restart/drain/zero readback, trusted receiver cleanup acceptance,
and approved Windows consent/UAC/lease-expiry acceptance. Full Rust/image gates
are left to CI for this Python/docs-only change. No deployed runtime is claimed.
The smallest next step is to integrate this policy in the authoritative session
service and prepare the reviewed infra workflow change with current read access.
