
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Dict, Optional
import uuid

app = FastAPI(title="Payment Service")

class PaymentIntent(BaseModel):
    id: str
    orderId: str
    amount: float
    currency: str
    status: str  # requires_confirmation | authorized | captured | canceled

class Charge(BaseModel):
    id: str
    intentId: str
    amount: float
    status: str  # captured | refunded

INTENTS: Dict[str, PaymentIntent] = {}
CHARGES: Dict[str, Charge] = {}
IDEMPOTENCY: Dict[str, str] = {}  # maps key -> intentId

@app.get("/health")
def health():
    return {"status": "ok", "service": "Payment Service"}

@app.post("/intents", response_model=PaymentIntent)
def create_intent(payload: dict, Idempotency_Key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
    order_id = payload.get("orderId")
    amount = float(payload.get("amount"))
    currency = payload.get("currency", "INR")

    if Idempotency_Key and Idempotency_Key in IDEMPOTENCY:
        # Return existing
        intent_id = IDEMPOTENCY[Idempotency_Key]
        return INTENTS[intent_id]

    intent_id = str(uuid.uuid4())
    intent = PaymentIntent(id=intent_id, orderId=order_id, amount=amount, currency=currency, status="requires_confirmation")
    INTENTS[intent_id] = intent

    if Idempotency_Key:
        IDEMPOTENCY[Idempotency_Key] = intent_id

    return intent

@app.post("/intents/{intent_id}/confirm", response_model=PaymentIntent)
def confirm_intent(intent_id: str):
    intent = INTENTS.get(intent_id)
    if not intent:
        raise HTTPException(404, detail="Intent not found")
    if intent.status not in ("requires_confirmation",):
        return intent  # idempotent
    intent.status = "authorized"
    INTENTS[intent_id] = intent
    return intent

@app.post("/intents/{intent_id}/capture", response_model=Charge)
def capture_intent(intent_id: str):
    intent = INTENTS.get(intent_id)
    if not intent:
        raise HTTPException(404, detail="Intent not found")
    if intent.status != "authorized":
        raise HTTPException(409, detail="Intent not authorized")
    # create charge
    charge_id = str(uuid.uuid4())
    charge = Charge(id=charge_id, intentId=intent_id, amount=intent.amount, status="captured")
    CHARGES[charge_id] = charge
    intent.status = "captured"
    INTENTS[intent_id] = intent
    return charge

@app.post("/charges/{charge_id}/refund", response_model=Charge)
def refund(charge_id: str):
    ch = CHARGES.get(charge_id)
    if not ch:
        raise HTTPException(404, detail="Charge not found")
    if ch.status == "refunded":
        return ch
    ch.status = "refunded"
    CHARGES[charge_id] = ch
    return ch
