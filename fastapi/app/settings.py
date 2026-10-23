import os


def get_port() -> int:
    """Use the cloud platform's PORT, or the local container default."""
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError as error:
        raise ValueError("PORT must be an integer between 1 and 65535") from error
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be an integer between 1 and 65535")
    return port
