"""Refresh pip compatibility exports from uv.lock, including the CPU wheel index."""

import subprocess
from pathlib import Path


def main():
    for name, extra in (("requirements.txt", ["--no-dev"]), ("requirements-test.txt", [])):
        subprocess.run(
            ["uv", "export", "--frozen", "--no-emit-project", "-o", name, *extra],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        path = Path(name)
        text = path.read_text(encoding="utf-8")
        path.write_text(
            "# CPU source added by scripts.export_requirements; hashes are from uv.lock.\n"
            "--extra-index-url https://download.pytorch.org/whl/cpu\n" + text,
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
