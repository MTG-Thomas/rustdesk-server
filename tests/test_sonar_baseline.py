"""Validate bootstrap identities and reject failed or foreign compute tasks."""
import base64
import io
import importlib.util
import urllib.error
import urllib.parse
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
        self.receipt = self.root / "baseline" / ".scannerwork" / "report-task.txt"
        self.receipt.parent.mkdir(parents=True)
        root_patch = patch.object(MODULE, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        self.receipt.write_text("projectKey=MTG-Thomas_rustdesk-server\nceTaskId=task\n")
        mocked = patch.dict(os.environ, {"BASELINE_BRANCH": "master", "GITHUB_OUTPUT": str(self.output)})
        mocked.start()
        self.addCleanup(mocked.stop)

    def execute(self, command):
        with patch.object(MODULE.sys, "argv", ["sonar_baseline.py", command]):
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

    def test_successful_task_matches_original_source(self):
        responses = [{"task": {"componentKey": MODULE.PROJECT, "status": "SUCCESS", "analysisId": "analysis"}}, {"analyses": [{"key": "analysis", "revision": MODULE.BASELINES["master"]}]}]
        with patch.object(MODULE, "request", side_effect=responses):
            self.execute("wait")

    def test_pending_task_is_polled_before_success(self):
        responses = [{"task": {"componentKey": MODULE.PROJECT, "status": "PENDING"}}, {"task": {"componentKey": MODULE.PROJECT, "status": "SUCCESS", "analysisId": "analysis"}}, {"analyses": [{"key": "analysis", "revision": MODULE.BASELINES["master"]}]}]
        with patch.object(MODULE, "request", side_effect=responses), patch.object(MODULE.time, "sleep") as sleep:
            self.execute("wait")
            sleep.assert_called_once_with(5)

    def test_pending_task_times_out(self):
        with patch.object(MODULE, "request", return_value={"task": {"componentKey": MODULE.PROJECT, "status": "IN_PROGRESS"}}), patch.object(MODULE.time, "sleep") as sleep:
            with self.assertRaisesRegex(SystemExit, "remains pending"):
                self.execute("wait")
            self.assertEqual(sleep.call_count, 60)

    def test_foreign_compute_task_is_rejected(self):
        with patch.object(MODULE, "request", return_value={"task": {"componentKey": "other", "status": "SUCCESS"}}):
            with self.assertRaisesRegex(SystemExit, "another project"):
                self.execute("wait")

    def test_receipt_path_cannot_be_overridden(self):
        with patch.object(MODULE.sys, "argv", ["sonar_baseline.py", "wait", "../../other"]):
            with self.assertRaisesRegex(SystemExit, "Expected"):
                MODULE.main()

    def test_request_encodes_query_and_authenticates_with_timeout(self):
        response = io.BytesIO(b'{"branches": []}')
        with patch.dict(os.environ, {"SONAR_TOKEN": "test-only-credential"}), patch.object(MODULE.urllib.request, "urlopen", return_value=response) as opener:
            self.assertEqual(MODULE.request("project_branches/list", project=MODULE.PROJECT, branch="codex/websocket-registration"), {"branches": []})
        request = opener.call_args.args[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        self.assertEqual(query["branch"], ["codex/websocket-registration"])
        self.assertEqual(request.get_header("Authorization"), "Basic " + base64.b64encode(b"test-only-credential:").decode())
        self.assertEqual(opener.call_args.kwargs["timeout"], 30)

    def test_provider_error_propagates(self):
        with patch.dict(os.environ, {"SONAR_TOKEN": "test-only-credential"}), patch.object(MODULE.urllib.request, "urlopen", side_effect=urllib.error.URLError("provider unavailable")):
            with self.assertRaises(urllib.error.URLError):
                MODULE.request("project_branches/list", project=MODULE.PROJECT)

    def test_missing_analysis_is_not_success(self):
        with patch.object(MODULE, "request", return_value={"analyses": []}):
            with self.assertRaisesRegex(SystemExit, "identity differs"):
                MODULE.verify_analysis("master", {"analysisId": "analysis"})

    def test_other_analysis_id_is_not_success(self):
        with patch.object(MODULE, "request", return_value={"analyses": [{"key": "other", "revision": MODULE.BASELINES["master"]}]}):
            with self.assertRaisesRegex(SystemExit, "identity differs"):
                MODULE.verify_analysis("master", {"analysisId": "analysis"})

    def test_receipt_preserves_equals_in_value_and_ignores_non_fields(self):
        self.receipt.write_text("projectKey=MTG-Thomas_rustdesk-server\nceTaskId=task=value\ncomment without separator\n")
        with patch.object(MODULE, "request", return_value={"task": {"componentKey": MODULE.PROJECT, "status": "FAILED"}}) as request:
            with self.assertRaisesRegex(SystemExit, "failed"):
                self.execute("wait")
        request.assert_called_once_with("ce/task", id="task=value")


if __name__ == "__main__":
    unittest.main()
