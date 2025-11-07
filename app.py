# app.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import os
import httpx
import asyncio

app = FastAPI(title="Payment Service")

# Config
# DATABASE_SERVICE_URL = os.getenv("DATABASE_SERVICE_URL", "http://localhost:8000")
DATABASE_SERVICE_URL = os.getenv("DATABASE_SERVICE_URL", "http://192.168.105.2:30000")
# Controls whether this service will simulate processing immediately (sync).
# Set to "false" to let an external workflow update payment status.
PROCESS_PAYMENTS_SYNC = os.getenv("PROCESS_PAYMENTS_SYNC", "true").lower() != "false"

# HTTP client defaults
HTTPX_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Models
class PaymentIn(BaseModel):
    id: str
    order_id: str
    amount: float
    status: str  # e.g. "pending", "completed", "failed"

class PaymentOut(PaymentIn):
    pass

# Helpers
async def db_request(method: str, path: str, json: Optional[dict] = None) -> dict:
    """
    Single-call wrapper to talk to the Database service.
    Raises HTTPException with meaningful status/detail on errors.
    """
    url = f"{DATABASE_SERVICE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            resp = await client.request(method, url, json=json)
    except httpx.ConnectTimeout:
        raise HTTPException(status_code=504, detail=f"Timeout connecting to database service at {url}")
    except httpx.ReadTimeout:
        raise HTTPException(status_code=504, detail=f"Timeout reading response from database service at {url}")
    except httpx.NetworkError as e:
        raise HTTPException(status_code=502, detail=f"Network error contacting database service at {url}: {e}")

    # propagate DB-side HTTP errors as-is
    if resp.status_code >= 400:
        # try parse detail from DB
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise HTTPException(status_code=resp.status_code, detail=detail)

    return resp.json() if resp.content else {}

# Simulate a simple payment gateway (synchronous) — returns status string
def _simulate_payment_processing(amount: float) -> str:
    # simple rule: amount > 0 => completed; otherwise failed
    try:
        if amount is None:
            return "failed"
        if amount > 0:
            return "completed"
        return "failed"
    except Exception:
        return "failed"

# -------------------------
# Helper: best-effort annotate order with refund metadata (uses safe DB endpoint if present)
# -------------------------
async def _record_refund_on_order_best_effort(order_id: str, payment_id: str, success: bool, error_msg: Optional[str] = None):
    """
    Best-effort: try to annotate the order in DB about refund outcome.
    Preferentially calls /orders/{oid}/refund-metadata if available (safer),
    otherwise falls back to fetching the order and PUTting modified payload (also best-effort).
    All failures are swallowed so refund primary operation stays authoritative.
    """
    if not order_id:
        return

    # Try dedicated safe endpoint first (recommended)
    try:
        payload = {
            "refund_attempt": {"payment_id": payment_id, "success": success, "error": error_msg},
            "payment_refund_status": "refunded" if success else "refund_failed"
        }
        # If DB service exposes this endpoint, it will handle partial updates safely.
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            url = f"{DATABASE_SERVICE_URL}/orders/{order_id}/refund-metadata"
            resp = await client.post(url, json=payload)
            if resp.status_code < 400:
                return
            # else fall-through to fallback approach
    except Exception:
        # ignore and try fallback
        pass

    # Fallback: fetch and update full order (may fail if DB schema is strict)
    try:
        order = await db_request("GET", f"/orders/{order_id}")
        order["refund_attempt"] = {"payment_id": payment_id, "success": success, "error": error_msg}
        order["payment_refund_status"] = "refunded" if success else "refund_failed"
        # Try to persist; if DB rejects unknown keys this may 4xx — swallow
        try:
            await db_request("PUT", f"/orders/{order_id}", json=order)
        except HTTPException:
            pass
    except Exception:
        pass

# Public API

@app.get("/health")
def health():
    return {"status": "ok", "service": "Payment Service"}

@app.post("/payments", response_model=PaymentOut, status_code=201)
async def create_payment(payload: PaymentIn):
    """
    Create a payment record (idempotent). If PROCESS_PAYMENTS_SYNC is true and
    incoming status is 'pending', simulate processing and update the stored record.
    """
    # 1) If payment exists already in DB, return it (idempotent)
    try:
        existing = await db_request("GET", f"/payments/{payload.id}")
        # DB returned existing payment
        return existing
    except HTTPException as e:
        if e.status_code != 404:
            # any other DB error -> propagate
            raise

    # 2) Not existing -> insert into DB
    payment_dict = payload.dict()
    await db_request("POST", "/payments", json=payment_dict)

    # 3) Optionally simulate processing synchronously
    if PROCESS_PAYMENTS_SYNC and payment_dict.get("status", "").lower() == "pending":
        # simulate synchronous processing (fast local CPU work)
        new_status = _simulate_payment_processing(payment_dict.get("amount", 0.0))
        if new_status != payment_dict.get("status"):
            # update DB record
            updated = {**payment_dict, "status": new_status}
            try:
                await db_request("PUT", f"/payments/{payload.id}", json=updated)
                return updated
            except HTTPException:
                # if update fails, return inserted record (best-effort)
                pass

    return payment_dict

@app.get("/payments/{pid}", response_model=PaymentOut)
async def get_payment(pid: str):
    p = await db_request("GET", f"/payments/{pid}")
    return p

@app.put("/payments/{pid}", response_model=PaymentOut)
async def update_payment(pid: str, payload: PaymentIn):
    # Ensure resource exists
    try:
        _ = await db_request("GET", f"/payments/{pid}")
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(404, detail="Payment not found")
        raise
    # Update in DB
    await db_request("PUT", f"/payments/{pid}", json=payload.dict())
    return payload.dict()

@app.get("/payments", response_model=List[PaymentOut])
async def list_payments():
    items = await db_request("GET", "/payments")
    return items

# --- refund endpoint ---
@app.post("/payments/{pid}/refund", response_model=PaymentOut)
async def refund_payment(pid: str):
    """
    Idempotent refund endpoint.
    - If payment not found -> 404
    - If payment already refunded/voided -> return current record (200)
    - Otherwise attempt refund (simulate or call gateway), update payment status to 'refunded',
      persist to DB, and best-effort annotate the related order with refund metadata.
    """
    # 1) fetch payment
    try:
        payment = await db_request("GET", f"/payments/{pid}")
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(status_code=404, detail="Payment not found")
        raise

    # 2) idempotent: if already refunded/voided, return existing
    pstatus = (payment.get("status") or "").lower()
    if pstatus in ("refunded", "voided"):
        return payment

    # 3) perform the refund (simulate here).
    # For simulation we assume refunds always succeed for amount > 0.
    amount = payment.get("amount", 0.0)
    refund_success = False
    refund_error = None
    try:
        # simulate refund logic
        if amount is None or amount <= 0:
            # treat as failed for <=0 (customize as needed)
            refund_success = False
            refund_error = "Invalid amount for refund"
        else:
            # simulate successful refund
            refund_success = True
    except Exception as e:
        refund_success = False
        refund_error = str(e)

    # 4) update payment status in DB accordingly
    if refund_success:
        payment["status"] = "refunded"
    else:
        # keep status as-is or set 'refund_failed' - choose your policy
        payment["status"] = "refund_failed"

    try:
        await db_request("PUT", f"/payments/{pid}", json=payment)
    except HTTPException as e:
        # If DB update failed, propagate as 502/500 to let caller know
        raise HTTPException(status_code=502, detail=f"Failed to persist payment refund status: {e.detail}")

    # 5) annotate order (best-effort)
    order_id = payment.get("order_id")
    try:
        await _record_refund_on_order_best_effort(order_id, pid, refund_success, refund_error)
    except Exception:
        # ignore any errors here to keep refund itself primary
        pass

    # 6) return updated payment record (fresh read)
    updated = await db_request("GET", f"/payments/{pid}")
    return updated

