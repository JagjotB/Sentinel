from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Sentinel checkout simulator")


class CheckoutRequest(BaseModel):
    cart_id: str = Field(min_length=1, max_length=64)
    amount_cents: int = Field(gt=0, le=1_000_000)


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "checkout"}


@app.post("/checkout")
def checkout(request: CheckoutRequest) -> dict[str, str | int]:
    return {"status": "accepted", "cart_id": request.cart_id, "amount_cents": request.amount_cents}
