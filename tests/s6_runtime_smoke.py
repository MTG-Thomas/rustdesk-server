"""Verify the final image boots both S6 services and stops cleanly."""

import subprocess
import sys
import time
import uuid


def docker(*args, timeout=30, check=True):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True,
        timeout=timeout, check=check,
    )


def main(image):
    name = "quick-support-s6-test-" + uuid.uuid4().hex
    try:
        docker(
            "run", "-d", "--name", name, "--network", "none",
            "--tmpfs", "/data", "-e", "RELAY=localhost", "-e", "ENCRYPTED_ONLY=1",
            image,
        )
        deadline = time.monotonic() + 30
        while True:
            result = docker("exec", name, "/usr/bin/healthcheck.sh", check=False)
            if result.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Both S6 services did not become ready")
            time.sleep(1)
        version = docker("exec", name, "/bin/busybox").stdout.splitlines()[0]
        if not version.startswith("BusyBox v1.37.0"):
            raise RuntimeError("Final image does not contain the tested BusyBox")
        docker("stop", "--time", "10", name, timeout=20)
        exit_code = docker("inspect", "--format", "{{.State.ExitCode}}", name).stdout.strip()
        if exit_code != "0":
            raise RuntimeError(f"S6 exited with {exit_code}; graceful shutdown failed")
        print("Final image: patched BusyBox, both S6 services ready, clean shutdown")
    finally:
        docker("rm", "-f", "-v", name, check=False)


if __name__ == "__main__":
    main(sys.argv[1])
