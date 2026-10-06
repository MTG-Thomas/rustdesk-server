"""Exercise patch provenance, repeat application, and dirty-work protection."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class CommonPatchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rustdesk-patch-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT / "patches", self.root / "patches")
        (self.root / "scripts").mkdir()
        shutil.copy(ROOT / "scripts/apply_common_patch.py", self.root / "scripts")
        self.manifest = json.loads((self.root / "patches/hbb-common/manifest.json").read_text())
        for name in self.manifest["files"]:
            path = self.root / "libs/hbb_common" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output([
                "git", "-C", str(ROOT / "libs/hbb_common"), "show",
                f"{self.manifest['revision']}:{name}",
            ]))

    def apply(self):
        return subprocess.run(
            ["python3", str(self.root / "scripts/apply_common_patch.py")],
            capture_output=True, text=True, check=False,
        )

    def test_exact_patch_is_repeatable(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already applied", result.stdout)

    def test_modified_preimage_is_preserved(self):
        name = next(iter(self.manifest["files"]))
        path = self.root / "libs/hbb_common" / name
        original = path.read_bytes() + b"\n# unrelated local edit\n"
        path.write_bytes(original)
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(path.read_bytes(), original)

    def test_modified_patch_is_rejected(self):
        patch = self.root / "patches/hbb-common/maintenance.patch"
        patch.write_bytes(patch.read_bytes() + b"\n")
        self.assertNotEqual(self.apply().returncode, 0)


if __name__ == "__main__":
    unittest.main()
