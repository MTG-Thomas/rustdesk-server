"""Start a disposable hbbs, then exercise real WS and UDP protocol boundaries."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

binary = Path(sys.argv[1]).resolve()
tests = Path(__file__).with_name('websocket_registration.py')
with tempfile.TemporaryDirectory(prefix='rustdesk-ws-test-') as directory:
    log_path = Path(directory) / 'hbbs.log'
    with log_path.open('w+') as log:
        server = subprocess.Popen([str(binary), '-k', '_', '-r', 'localhost:21117'], cwd=directory, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 20
            while True:
                if server.poll() is not None:
                    raise RuntimeError('Test server exited during startup')
                try:
                    with socket.create_connection(('127.0.0.1', 21118), timeout=1):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Test server failed to bind its WS port')
                    time.sleep(0.1)
            env = dict(os.environ, HBBS_PUBLIC_KEY=(Path(directory) / 'id_ed25519.pub').read_text().strip())
            result = subprocess.run([sys.executable, str(tests)], env=env)
            if result.returncode:
                log.flush()
                print(log_path.read_text(), file=sys.stderr)
            sys.exit(result.returncode)
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
