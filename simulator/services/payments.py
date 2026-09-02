from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Sentinel payments simulator")


class ChargeRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=64)
    amount_cents: int = Field(gt=0, le=1_000_000)


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "payments"}


@app.post("/charge")
def charge(request: ChargeRequest) -> dict[str, str | int]:
    return {
        "status": "authorized",
        "order_id": request.order_id,
        "amount_cents": request.amount_cents,
    }
