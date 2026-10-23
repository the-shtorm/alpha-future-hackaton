import uvicorn

from app.settings import get_port


def main() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=get_port())


if __name__ == "__main__":
    main()
