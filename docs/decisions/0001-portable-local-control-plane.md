# ADR 0001: Portable local control plane

- Status: accepted
- Date: 2026-09-02

## Context

Sentinel must run without paid services while preserving a production deployment path. Requiring Docker,
PostgreSQL, Redis, kind, and a hosted model for every unit test would make the core runtime difficult to
review and reproduce.

## Decision

The supported zero-dependency data path uses SQLite, deterministic model adapters, and simulator-backed
tool providers. SQLAlchemy keeps the same repository compatible with PostgreSQL, which is the container
deployment default. Redis is optional because the initial worker uses durable database leases and
idempotency records. The Kubernetes, telemetry, Git, and knowledge APIs share the same typed audited tool
contracts whether their provider is the simulator or a live system.

The telemetry neural model is a compact NumPy temporal autoencoder with explicit backpropagation. This
keeps training deterministic on Python 3.12 without a multi-hundred-megabyte accelerator runtime. A model
artifact is trained and evaluated by the same code used during incident inference. The interface is
deliberately compatible with adding a PyTorch implementation later.

## Consequences

- Reviewers can run the complete deterministic demo with Python and Node only.
- Production-shaped PostgreSQL and Kubernetes manifests remain available and tested at contract level.
- The local simulator is not evidence that a real cluster integration has production credentials.
- The NumPy backend demonstrates the learning algorithm but does not offer GPU acceleration.

