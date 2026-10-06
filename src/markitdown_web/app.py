# SPDX-FileCopyrightText: markitdown-web is an unofficial companion package.
# The underlying MarkItDown library is (c) Microsoft Corporation, MIT License.

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .__about__ import __version__
from .config import Settings
from .service import ConversionService, build_zip

STATIC_DIR = Path(__file__).parent / "static"

_READ_CHUNK = 1024 * 1024

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    ),
}


class ZipEntry(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    markdown: str


class ZipRequest(BaseModel):
    files: List[ZipEntry]


def create_app(
    settings: Optional[Settings] = None,
    *,
    service: Optional[ConversionService] = None,
    local_only: Optional[bool] = None,
) -> FastAPI:
    cfg: Settings = settings or Settings.from_env()
    svc: ConversionService = service or ConversionService(cfg)
    if local_only is None:
        local_only = cfg.local_only

    app = FastAPI(
        title="markitdown-web",
        version=__version__,
        docs_url="/api/docs" if cfg.enable_api_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if cfg.enable_api_docs else None,
    )
    app.state.settings = cfg
    app.state.service = svc

    @app.middleware("http")
    async def harden_request(request: Request, call_next):
        if local_only and not _is_loopback_host(request.headers.get("host")):
            return JSONResponse(
                status_code=403,
                content={
                    "detail": "Requests must target localhost. This server only "
                    "accepts loopback traffic."
                },
            )
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "service": "markitdown-web",
            "version": __version__,
            "limits": {
                "max_files": cfg.max_files,
                "max_file_bytes": cfg.max_file_bytes,
                "max_total_bytes": cfg.max_total_bytes,
                "max_markdown_chars": cfg.max_markdown_chars,
            },
        }

    @app.post("/api/convert")
    async def convert(
        files: List[UploadFile] = File(..., description="Files to convert")
    ) -> JSONResponse:
        if len(files) == 0:
            raise HTTPException(status_code=400, detail="No files were uploaded.")
        if len(files) > cfg.max_files:
            raise HTTPException(
                status_code=413,
                detail=f"Too many files: {len(files)} > {cfg.max_files}.",
            )

        uploads: List[dict] = []
        total_bytes = 0
        for upload in files:
            data = await _read_limited(upload, cfg.max_file_bytes)
            total_bytes += len(data)
            if total_bytes > cfg.max_total_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"Request exceeds the {cfg.max_total_bytes} byte " "limit.",
                )
            uploads.append(
                {
                    "filename": upload.filename or "upload.bin",
                    "content_type": upload.content_type,
                    "data": data,
                }
            )

        # Conversion is CPU-bound and synchronous: move it off the event loop.
        outcomes = await run_in_threadpool(svc.convert_all, uploads)

        results = [outcome.to_public_dict() for outcome in outcomes]
        succeeded = sum(1 for outcome in outcomes if outcome.ok)
        return JSONResponse(
            content={
                "results": results,
                "summary": {
                    "total": len(results),
                    "succeeded": succeeded,
                    "failed": len(results) - succeeded,
                },
            }
        )

    @app.post("/api/zip")
    async def convert_to_zip(request: Request) -> Response:
        body = await request.body()
        budget = cfg.max_markdown_chars * cfg.max_files
        if len(body) > max(budget, cfg.max_total_bytes):
            raise HTTPException(status_code=413, detail="ZIP payload is too large.")

        try:
            payload = ZipRequest.model_validate_json(body)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid ZIP payload: {exc.errors()[0]['loc']} "
                f"{exc.errors()[0]['msg']}",
            ) from exc
        if len(payload.files) > cfg.max_files:
            raise HTTPException(
                status_code=413,
                detail=f"Too many files: {len(payload.files)} > {cfg.max_files}.",
            )

        outcomes = await run_in_threadpool(_outcomes_from_payload, payload, cfg)
        archive = await run_in_threadpool(build_zip, outcomes)
        return Response(
            content=archive,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="markitdown-output.zip"'
            },
        )

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


def _outcomes_from_payload(payload: ZipRequest, settings: Settings):
    """Rebuild conversion outcomes from client-provided markdown payloads."""
    from .service import ConversionOutcome, reserve_output_name

    used: set = set()
    outcomes = []
    for entry in payload.files:
        markdown = entry.markdown
        truncated = False
        if len(markdown) > settings.max_markdown_chars:
            markdown = (
                markdown[: settings.max_markdown_chars]
                + "\n\n<!-- markitdown-web: output truncated at "
                f"{settings.max_markdown_chars} characters -->\n"
            )
            truncated = True
        outcomes.append(
            ConversionOutcome(
                filename=entry.filename,
                output_name=reserve_output_name(entry.filename, used),
                ok=True,
                size_bytes=0,
                elapsed_ms=0,
                markdown=markdown,
                truncated=truncated,
            )
        )
    return outcomes


async def _read_limited(upload: UploadFile, max_bytes: int) -> bytes:
    """Read an upload in chunks, rejecting anything over `max_bytes`."""
    chunks: List[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File '{upload.filename or 'upload.bin'}' exceeds the "
                f"{max_bytes} byte limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _is_loopback_host(host_header: Optional[str]) -> bool:
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):  # IPv6 literal, possibly with a port
        host = host.split("]")[0].lstrip("[")
    else:
        host = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    return host in ("localhost", "127.0.0.1", "::1")
