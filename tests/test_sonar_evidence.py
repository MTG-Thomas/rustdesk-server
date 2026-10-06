"""Reject coverage copied from another source or modified after production."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("sonar_evidence", Path(__file__).resolve().parents[1] / "scripts/sonar_evidence.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SonarEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for folder in ("artifacts", "src", "patches/hbb-common"):
            (self.root / folder).mkdir(parents=True)
        (self.root / "src/main.rs").write_text("fn main() {}")
        (self.root / "patches/hbb-common/manifest.json").write_text("{}")
        (self.root / "artifacts/lcov.info").write_text("SF:src/main.rs\nDA:1,1\nend_of_record\n")
        (self.root / "artifacts/clippy.json").write_text("{}\n")
        (self.root / "artifacts/python-coverage.xml").write_text("<coverage/>")
        for mocked in (patch.object(MODULE, "ROOT", self.root), patch.dict(os.environ, {"SOURCE_SHA": "candidate", "BASE_SHA": "base"}), patch.object(MODULE.subprocess, "check_output", return_value="candidate\n")):
            mocked.start()
            self.addCleanup(mocked.stop)

    def execute(self, command):
        with patch.object(MODULE.sys, "argv", ["sonar_evidence.py", command]):
            MODULE.main()

    def test_same_source_and_reports_verify(self):
        self.execute("write")
        self.execute("verify")

    def test_modified_report_is_rejected(self):
        self.execute("write")
        (self.root / "artifacts/clippy.json").write_text("changed")
        with self.assertRaisesRegex(SystemExit, "digest mismatch"):
            self.execute("verify")

    def test_other_head_is_rejected(self):
        with patch.dict(os.environ, {"SOURCE_SHA": "other"}):
            with self.assertRaisesRegex(SystemExit, "differs"):
                self.execute("write")

    def test_other_base_is_rejected(self):
        self.execute("write")
        with patch.dict(os.environ, {"BASE_SHA": "other"}):
            with self.assertRaisesRegex(SystemExit, "mismatch"):
                self.execute("verify")

    def test_missing_or_external_source_is_rejected(self):
        (self.root / "artifacts/lcov.info").write_text("SF:src/../../external.rs\n")
        with self.assertRaisesRegex(SystemExit, "outside"):
            self.execute("write")

    def test_empty_coverage_is_rejected(self):
        (self.root / "artifacts/lcov.info").write_text("")
        with self.assertRaisesRegex(SystemExit, "Missing measured"):
            self.execute("write")

    def test_coverage_without_server_source_is_rejected(self):
        (self.root / "artifacts/lcov.info").write_text("SF:tests/test.rs\n")
        with self.assertRaisesRegex(SystemExit, "Missing measured"):
            self.execute("write")

    def test_unrecognized_command_is_rejected(self):
        with self.assertRaisesRegex(SystemExit, "Expected write or verify"):
            self.execute("skip")

    def test_missing_report_is_rejected(self):
        (self.root / "artifacts/python-coverage.xml").unlink()
        with self.assertRaises(FileNotFoundError):
            self.execute("write")


if __name__ == "__main__":
    unittest.main()
