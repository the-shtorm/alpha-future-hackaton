"""Start an isolated loopback Uvicorn process, smoke it, and always stop it."""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {
        **os.environ,
        "ML_INTERNAL_API_KEY": secrets.token_hex(32),
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    Path("reports").mkdir(exist_ok=True)
    with Path("reports/http-server.log").open("w", encoding="utf-8") as logs:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            env=env,
            stdout=logs,
            stderr=logs,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 90
            while True:
                if process.poll() is not None:
                    raise RuntimeError("Server failed startup; inspect reports/http-server.log")
                try:
                    with urlopen(url + "/health/ready", timeout=1) as response:
                        if response.status == 200:
                            break
                except (URLError, TimeoutError):
                    pass
                if time.monotonic() >= deadline:
                    raise TimeoutError("Server did not become ready in 90 seconds")
                time.sleep(0.2)
            result = subprocess.run(
                [sys.executable, "-m", "scripts.http_smoke", "--url", url],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            report = json.loads(result.stdout)
            report["transport"] = "TCP loopback; separate Uvicorn process; offline model"
            Path("reports/http-smoke.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report))
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
