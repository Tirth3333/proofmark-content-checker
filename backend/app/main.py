from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import engine
from .config import settings
from .extract import ExtractionError, extract
from .llm.providers import get_provider
from .llm.verify import search_configured
from .models import AnalyzeRequest, AnalyzeResponse, ExtractRequest, ExtractResponse

app = FastAPI(title="Content Quality & Factuality Checker", version="1.0.0")
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"]
)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    msgs = []
    for e in exc.errors():
        m = str(e.get("msg", "Invalid input")).removeprefix("Value error, ")
        loc = ".".join(str(x) for x in e.get("loc", [])[1:])
        msgs.append(m if loc in ("text", "") else f"{loc}: {m}")
    return JSONResponse(status_code=422, content={"detail": " ".join(msgs)})


@app.get("/api/health")
async def health() -> dict:
    provider, reason = get_provider()
    ok, sp = search_configured()
    return {
        "status": "ok",
        "ai": {"enabled": provider is not None, "provider": getattr(provider, "name", "none"), "message": reason},
        "verification": {"enabled": ok, "provider": sp},
        "limits": {"max_chars": settings.max_chars},
    }


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest) -> AnalyzeResponse:
    return await engine.analyze(req)


@app.post("/api/extract", response_model=ExtractResponse)
async def extract_url(req: ExtractRequest) -> ExtractResponse:
    try:
        url, title, text = await extract(req.url)
    except ExtractionError as e:
        raise HTTPException(status_code=e.status, detail=str(e)) from e
    return ExtractResponse(url=url, title=title, text=text, characters=len(text))


# Serve the built frontend when present (single-service deployment).
_dist = Path(os.getenv("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if _dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        f = _dist / path
        if path and f.is_file() and _dist in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(_dist / "index.html")
