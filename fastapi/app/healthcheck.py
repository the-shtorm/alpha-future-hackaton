from urllib.request import urlopen

from app.settings import get_port


def main() -> None:
    with urlopen(f"http://127.0.0.1:{get_port()}/health", timeout=2) as response:
        if response.status != 200:
            raise RuntimeError("Health endpoint did not return HTTP 200")


if __name__ == "__main__":
    main()
