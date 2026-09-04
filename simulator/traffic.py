from __future__ import annotations

import asyncio
import json
import os
import secrets
import time

import httpx


async def generate() -> None:
    target = os.getenv("TARGET_URL", "http://checkout:8080/work")
    rate = max(0.2, float(os.getenv("REQUESTS_PER_SECOND", "2")))
    interval = 1.0 / rate
    async with httpx.AsyncClient(timeout=3.0) as client:
        while True:
            request_id = f"load-{secrets.token_hex(8)}"
            started = time.perf_counter()
            status = 0
            error = ""
            try:
                response = await client.post(
                    target,
                    json={
                        "request_id": request_id,
                        "amount_cents": 1500,
                        "schema_version": "v1",
                    },
                    headers={"traceparent": secrets.token_hex(16)},
                )
                status = response.status_code
            except httpx.HTTPError as exc:
                error = type(exc).__name__
            print(
                json.dumps(
                    {
                        "event": "traffic_request",
                        "target": target,
                        "status": status,
                        "error": error,
                        "duration_ms": (time.perf_counter() - started) * 1000,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            await asyncio.sleep(interval)


def main() -> None:
    asyncio.run(generate())


if __name__ == "__main__":
    main()
