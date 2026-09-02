from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes.incidents import router as incidents_router
from api.routes.simulator import router as simulator_router
from api.schemas.incidents import ErrorOut
from persistence.repository import ConflictError, NotFoundError


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


app = FastAPI(
    title="Sentinel Reliability Engineering API",
    version="0.1.0",
    description="Durable evidence-backed incident investigation control plane.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Idempotency-Key",
        "X-Approval-Token",
    ],
)
app.include_router(incidents_router)
app.include_router(simulator_router)


@app.exception_handler(NotFoundError)
async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    payload = ErrorOut(code="not_found", message=str(exc), request_id=secrets.token_hex(8))
    return JSONResponse(status_code=404, content=payload.model_dump(mode="json"))


@app.exception_handler(ConflictError)
async def conflict(_: Request, exc: ConflictError) -> JSONResponse:
    payload = ErrorOut(code="conflict", message=str(exc), request_id=secrets.token_hex(8))
    return JSONResponse(status_code=409, content=payload.model_dump(mode="json"))


@app.get("/healthz", tags=["operations"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sentinel-api"}


def run() -> None:
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
