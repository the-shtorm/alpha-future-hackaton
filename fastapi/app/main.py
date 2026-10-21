from fastapi import FastAPI

app = FastAPI(
    title="Credit Cabinet FastAPI",
    description="Initial service scaffold. Business endpoints are not implemented yet.",
    version="0.1.0",
)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Report process health; this does not check database availability."""
    return {"status": "ok"}
