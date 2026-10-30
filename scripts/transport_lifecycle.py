"""Nonsecret v1 transport policy seam; caller supplies authoritative, durable state.

No Azure mutations or customer activation. Serialize calls per endpoint in the
session authority; persist state and receipts atomically before acting on them.
"""
from dataclasses import dataclass, field


@dataclass
class Lease:
    session_id: str
    expires_at: int
    revoked: bool = False
    cleanup_accepted: bool = False


@dataclass
class Transport:
    generation: int
    key_fingerprint: str
    leases: dict[str, Lease] = field(default_factory=dict)
    draining: bool = False

    def prepare(self, session_id, lease_id, expires_at, now):
        if not session_id or not lease_id or expires_at <= now:
            raise ValueError('nonempty identifiers and a future expiry are required')
        if self.draining:
            return self.receipt(session_id, lease_id, ['endpoint_draining'])
        previous = self.leases.get(lease_id)
        if previous:
            if previous != Lease(session_id, expires_at):
                raise ValueError('lease id cannot be reused or renewed implicitly')
        else:
            self.leases[lease_id] = Lease(session_id, expires_at)
        return self.receipt(session_id, lease_id, ['protocol_probes_required'], 'wake_required')

    def readiness(self, session_id, lease_id, now, *, generation,
                  key_fingerprint, hbbs_registered=False, hbbr_paired=False):
        lease = self._lease(session_id, lease_id)
        reasons = []
        if generation != self.generation:
            reasons.append('stale_generation')
        if not self.key_fingerprint or key_fingerprint != self.key_fingerprint:
            reasons.append('key_continuity_unverified')
        if not hbbs_registered:
            reasons.append('hbbs_registration_unverified')
        if not hbbr_paired:
            reasons.append('hbbr_bidirectional_relay_unverified')
        if lease.revoked or lease.expires_at <= now:
            reasons.append('lease_inactive')
        if self.draining:
            reasons.append('endpoint_draining')
        return self.receipt(session_id, lease_id, reasons)

    def revoke(self, session_id, lease_id):
        self._lease(session_id, lease_id).revoked = True
        return self.receipt(session_id, lease_id, ['cleanup_required'])

    def accept_cleanup(self, session_id, lease_id, *, generation):
        lease = self._lease(session_id, lease_id)
        if generation != self.generation or not lease.revoked:
            raise ValueError('cleanup must follow revoke in the current generation')
        lease.cleanup_accepted = True
        return self.receipt(session_id, lease_id, [], 'cleanup_accepted')

    def drain(self, session_id, lease_id, now):
        self._lease(session_id, lease_id)
        self.draining = True
        reasons = []
        # Expiry alone never proves disconnection or endpoint cleanup.
        if any(not lease.revoked or not lease.cleanup_accepted
               for lease in self.leases.values()):
            reasons.append('revoke_and_cleanup_required')
        if any(not lease.revoked and lease.expires_at > now
               for lease in self.leases.values()):
            reasons.append('active_leases')
        return self.receipt(session_id, lease_id, reasons, 'safe_to_zero')

    def restart(self, generation, key_fingerprint):
        if generation <= self.generation:
            raise ValueError('restart requires a monotonically increasing generation')
        if not self.key_fingerprint or key_fingerprint != self.key_fingerprint:
            raise ValueError('restart must preserve the pinned public key fingerprint')
        self.generation = generation
        # A replacement replica cannot attest cleanup from its predecessor.
        for lease in self.leases.values():
            lease.cleanup_accepted = False

    def _lease(self, session_id, lease_id):
        lease = self.leases.get(lease_id)
        if lease is None or lease.session_id != session_id:
            raise ValueError('unknown session/lease binding')
        return lease

    def receipt(self, session_id, lease_id, reasons, success='ready'):
        return dict(contract='rustdesk.transport.v1', session_id=session_id,
                    lease_id=lease_id, generation=self.generation,
                    state='blocked' if reasons else success, reasons=reasons,
                    action=success)
