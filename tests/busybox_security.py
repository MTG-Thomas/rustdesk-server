"""Exercise the three reported CVEs against an actual BusyBox executable."""

import io
from pathlib import Path
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest


BINARY = str(Path(sys.argv.pop(1)).resolve())


class BusyBoxSecurityTests(unittest.TestCase):
    def run_applet(self, *args):
        return subprocess.run(
            [BINARY, *args], capture_output=True, timeout=5, check=False
        )

    def test_ash_rejects_malformed_arithmetic_without_crashing(self):
        # Upstream regression trigger for bug 15216 / CVE-2022-48174.
        for expression in ("${0::0/0~09J}", "${0::" + "09v" * 1000 + "}"):
            with self.subTest(expression_length=len(expression)):
                result = self.run_applet("ash", "-c", "echo " + expression)
                self.assertIn(result.returncode, (1, 2), result.stderr)

    def test_tar_listing_escapes_terminal_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "fixture.tar"
            with tarfile.open(archive, "w", format=tarfile.USTAR_FORMAT) as writer:
                for name in ("visible", "hidden\x1b[2K\rname"):
                    entry = tarfile.TarInfo(name)
                    entry.size = 4
                    writer.addfile(entry, io.BytesIO(b"test"))
                entry = tarfile.TarInfo("link")
                entry.type = tarfile.SYMTYPE
                entry.linkname = "hidden\x1b[2K\rname"
                writer.addfile(entry)
            for option in ("-tf", "-tvf"):
                result = self.run_applet("tar", option, str(archive))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(b"visible", result.stdout)
                self.assertIn(b"hidden", result.stdout)
                self.assertNotIn(b"\x1b", result.stdout)
                self.assertNotIn(b"\r", result.stdout)

    def test_wget_rejects_every_raw_c0_control_and_space_before_connecting(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(0.1)
            port = listener.getsockname()[1]
            for value in range(1, 33):
                with self.subTest(value=value):
                    result = self.run_applet(
                        "wget", "-q", "-O", "-",
                        f"http://127.0.0.1:{port}/path{chr(value)}injected",
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(b"Unencoded control character", result.stderr)
                    with self.assertRaises(socket.timeout):
                        listener.accept()

    def test_wget_preserves_percent_encoded_paths(self):
        requests = []
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            listener.settimeout(5)
            port = listener.getsockname()[1]

            def serve():
                connection, _ = listener.accept()
                with connection:
                    connection.settimeout(5)
                    data = b""
                    while b"\r\n\r\n" not in data:
                        data += connection.recv(4096)
                    requests.append(data)
                    connection.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n"
                        b"Connection: close\r\n\r\nok"
                    )

            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            result = self.run_applet(
                "wget", "-q", "-O", "-", f"http://127.0.0.1:{port}/valid%20path"
            )
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b"ok")
            self.assertEqual(len(requests), 1)
            self.assertTrue(requests[0].startswith(b"GET /valid%20path HTTP/1.1\r\n"))


if __name__ == "__main__":
    unittest.main()
