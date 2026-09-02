from __future__ import annotations

from pydantic import BaseModel, Field


class NamespaceRequest(BaseModel):
    namespace: str = Field(default="sentinel-demo", pattern=r"^[a-z0-9-]+$")


class ResourceRequest(NamespaceRequest):
    service: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")


class RevisionRequest(BaseModel):
    revision: str = Field(min_length=4, max_length=64, pattern=r"^[a-zA-Z0-9._/-]+$")


class DiffRequest(BaseModel):
    base: str = Field(min_length=1, max_length=64)
    head: str = Field(min_length=1, max_length=64)


class PullRequestRequest(BaseModel):
    number: int = Field(gt=0, le=1_000_000)


class FileAtRevisionRequest(RevisionRequest):
    path: str = Field(min_length=1, max_length=300, pattern=r"^[a-zA-Z0-9_./-]+$")


class PatchRequest(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    path: str = Field(min_length=1, max_length=300, pattern=r"^[a-zA-Z0-9_./-]+$")
    patch: str = Field(min_length=3, max_length=20_000)


class MetricsQuery(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    start: float | None = None
    end: float | None = None


class LogSearch(BaseModel):
    service: str = Field(min_length=1, max_length=100)
    query: str = Field(default="", max_length=500)
    limit: int = Field(default=100, ge=1, le=1000)


class TraceRequest(BaseModel):
    trace_id: str = Field(min_length=8, max_length=64, pattern=r"^[a-fA-F0-9]+$")


class IncidentSearch(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=5, ge=1, le=50)


class IncidentRequest(BaseModel):
    incident_id: str = Field(min_length=3, max_length=100)


class StoreResolutionRequest(IncidentRequest):
    root_cause: str = Field(min_length=2, max_length=200)
    resolution: str = Field(min_length=3, max_length=2000)
    evidence_ids: list[str] = Field(min_length=1, max_length=100)
