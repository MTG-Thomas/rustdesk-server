"""Exercise the metadata guard with real ELF sections, including a decoy."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_auditable.py"


class AuditableTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="rustdesk-elf-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.payload = self.root / "metadata"
        self.payload.write_bytes(b"section-presence-fixture")
        self.original = Path(shutil.which("true"))

    def binary(self, section):
        output = self.root / "binary"
        subprocess.run(["objcopy", "--add-section", f"{section}={self.payload}", str(self.original), str(output)], check=True)
        return output

    def check(self, *binaries):
        return subprocess.run(["python3", str(SCRIPT), *map(str, binaries)], capture_output=True, text=True)

    def test_exact_section_is_required(self):
        self.assertEqual(self.check(self.binary(".dep-v0")).returncode, 0)

    def test_similarly_named_section_is_rejected(self):
        self.assertNotEqual(self.check(self.binary(".dep-v0-decoy")).returncode, 0)

    def test_every_binary_needs_metadata(self):
        self.assertNotEqual(self.check(self.binary(".dep-v0"), self.original).returncode, 0)

    def test_empty_input_is_rejected(self):
        self.assertNotEqual(self.check().returncode, 0)


if __name__ == "__main__":
    unittest.main()
