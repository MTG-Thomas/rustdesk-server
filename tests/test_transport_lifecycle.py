"""Executable policy tests; these do not claim live ACA or Windows acceptance."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from transport_lifecycle import Transport


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.transport = Transport(1, 'public-key-sha256')
        self.transport.prepare('session', 'lease', 100, 0)

    def ready(self, **changes):
        args = dict(generation=1, key_fingerprint='public-key-sha256',
                    hbbs_registered=True, hbbr_paired=True)
        args.update(changes)
        return self.transport.readiness('session', 'lease', 1, **args)

    def test_wake_requires_both_protocols(self):
        receipt = self.transport.prepare('second', 'second-lease', 100, 0)
        self.assertEqual(receipt['action'], 'wake_required')
        self.assertEqual(receipt['state'], 'blocked')
        self.assertEqual(self.ready()['state'], 'ready')
        for missing in ('hbbs_registered', 'hbbr_paired'):
            self.assertEqual(self.ready(**{missing: False})['state'], 'blocked')

    def test_overlapping_leases_protect_idle(self):
        self.transport.prepare('second', 'second-lease', 100, 0)
        self.transport.revoke('session', 'lease')
        self.transport.accept_cleanup('session', 'lease', generation=1)
        self.assertIn('active_leases', self.transport.drain('session', 'lease', 1)['reasons'])
        self.assertEqual(self.transport.prepare('third', 'third-lease', 100, 1)['reasons'],
                         ['endpoint_draining'])
        self.transport.revoke('second', 'second-lease')
        self.transport.accept_cleanup('second', 'second-lease', generation=1)
        self.assertEqual(self.transport.drain('session', 'lease', 1)['state'], 'safe_to_zero')

    def test_expiry_never_substitutes_for_cleanup(self):
        self.assertEqual(self.transport.drain('session', 'lease', 101)['state'], 'blocked')
        self.transport.revoke('session', 'lease')
        self.assertEqual(self.transport.drain('session', 'lease', 101)['state'], 'blocked')
        self.transport.accept_cleanup('session', 'lease', generation=1)
        self.assertEqual(self.transport.drain('session', 'lease', 101)['state'], 'safe_to_zero')

    def test_restart_invalidates_old_evidence_and_preserves_key(self):
        self.transport.revoke('session', 'lease')
        self.transport.accept_cleanup('session', 'lease', generation=1)
        with self.assertRaises(ValueError):
            self.transport.restart(2, 'different-key')
        self.transport.restart(2, 'public-key-sha256')
        self.assertIn('stale_generation', self.ready()['reasons'])
        self.assertEqual(self.transport.drain('session', 'lease', 1)['state'], 'blocked')
        with self.assertRaises(ValueError):
            self.transport.accept_cleanup('session', 'lease', generation=1)

    def test_binding_replay_and_revocation_fail_closed(self):
        with self.assertRaises(ValueError):
            self.transport.revoke('other-session', 'lease')
        with self.assertRaises(ValueError):
            self.transport.prepare('session', 'lease', 200, 0)
        with self.assertRaises(ValueError):
            self.transport.accept_cleanup('session', 'lease', generation=1)
        self.transport.revoke('session', 'lease')
        self.assertIn('lease_inactive', self.ready()['reasons'])
        with self.assertRaises(ValueError):
            self.transport.prepare('session', 'lease', 100, 0)


if __name__ == '__main__':
    unittest.main()
