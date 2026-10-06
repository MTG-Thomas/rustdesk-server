"""Validate bootstrap identities and reject failed or foreign compute tasks."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("sonar_baseline", Path(__file__).resolve().parents[1] / "scripts/sonar_baseline.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = self.root / "output"
        self.receipt = self.root / "report-task.txt"
        self.receipt.write_text("projectKey=MTG-Thomas_rustdesk-server\nceTaskId=task\n")
        mocked = patch.dict(os.environ, {"BASELINE_BRANCH": "master", "GITHUB_OUTPUT": str(self.output)})
        mocked.start()
        self.addCleanup(mocked.stop)

    def execute(self, command):
        with patch.object(MODULE.sys, "argv", ["sonar_baseline.py", command, str(self.receipt)]):
            MODULE.main()

    def test_missing_branch_requires_its_actual_original_source(self):
        with patch.dict(os.environ, {"BASELINE_BRANCH": "codex/websocket-registration"}), patch.object(MODULE, "request", return_value={"branches": [{"name": "master"}]}) as request:
            self.execute("inspect")
            request.assert_called_once()
        self.assertIn("needed=true", self.output.read_text())
        self.assertIn(MODULE.BASELINES["codex/websocket-registration"], self.output.read_text())

    def test_existing_analysis_is_preserved(self):
        with patch.object(MODULE, "request", side_effect=[{"branches": [{"name": "master"}]}, {"analyses": [{"key": "existing"}]}]):
            self.execute("inspect")
        self.assertIn("needed=false", self.output.read_text())

    def test_unknown_branch_is_rejected(self):
        with patch.dict(os.environ, {"BASELINE_BRANCH": "unknown"}):
            with self.assertRaisesRegex(SystemExit, "Unsupported"):
                self.execute("inspect")

    def test_other_source_analysis_is_rejected(self):
        responses = [{"task": {"componentKey": MODULE.PROJECT, "status": "SUCCESS", "analysisId": "analysis"}}, {"analyses": [{"key": "analysis", "revision": "other"}]}]
        with patch.object(MODULE, "request", side_effect=responses):
            with self.assertRaisesRegex(SystemExit, "identity differs"):
                self.execute("wait")

    def test_failed_compute_task_is_rejected(self):
        with patch.object(MODULE, "request", return_value={"task": {"componentKey": MODULE.PROJECT, "status": "FAILED"}}):
            with self.assertRaisesRegex(SystemExit, "failed"):
                self.execute("wait")

    def test_foreign_project_receipt_is_rejected(self):
        self.receipt.write_text("projectKey=other\nceTaskId=task\n")
        with self.assertRaisesRegex(SystemExit, "another project"):
            self.execute("wait")


if __name__ == "__main__":
    unittest.main()
