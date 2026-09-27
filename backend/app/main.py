from fastapi import FastAPI

app = FastAPI(title="Mziko API", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
