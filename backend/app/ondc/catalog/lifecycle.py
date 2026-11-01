"""Internal catalog lifecycle and ONDC order administration APIs."""
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.ondc.models import (CatalogPublicationState, ONDCOrder, ONDCOrderItem, OrderStateEvent,
                             FinancialEvent, ReturnRequest, CatalogSubscription, CatalogPublicationJob)
from app.ondc.admin_security import require_admin
from app.ondc.protocol.post_order import transition

router = APIRouter(prefix="/api/ondc", tags=["ONDC administration"])

class RejectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(min_length=1, max_length=30)
    message: str = Field(min_length=1, max_length=500)

@router.get("/catalog-state")
def catalog_state(db: Session = Depends(get_db)):
    return [{"entity_type": row.entity_type, "entity_id": row.entity_id, "state": row.state,
             "changed_at": row.changed_at, "published_at": row.published_at,
             "rejection_code": row.rejection_code, "rejection_message": row.rejection_message}
            for row in db.scalars(select(CatalogPublicationState).order_by(CatalogPublicationState.id))]

@router.put("/catalog-state/{entity_type}/{entity_id}/rejection")
def reject(entity_type: Literal["provider", "store", "product"], entity_id: int,
           payload: RejectionInput, db: Session = Depends(get_db), authenticated=Depends(require_admin)):
    row = db.scalar(select(CatalogPublicationState).where(
        CatalogPublicationState.entity_type == entity_type, CatalogPublicationState.entity_id == entity_id))
    if row is None:
        raise HTTPException(404, "Publication entity not found")
    row.state, row.rejection_code, row.rejection_message = "rejected", payload.code, payload.message
    db.commit()
    return {"entity_type": entity_type, "entity_id": entity_id, "state": row.state,
            "rejection_code": row.rejection_code, "rejection_message": row.rejection_message}

@router.get("/orders")
def orders(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0),
           db: Session = Depends(get_db)):
    rows = db.scalars(select(ONDCOrder).order_by(ONDCOrder.created_at.desc()).offset(offset).limit(limit)).all()
    result = []
    for row in rows:
        items = db.scalars(select(ONDCOrderItem).where(ONDCOrderItem.order_id == row.id)).all()
        history = db.scalars(select(OrderStateEvent).where(OrderStateEvent.order_id == row.id)
                             .order_by(OrderStateEvent.occurred_at)).all()
        finances = db.scalars(select(FinancialEvent).where(FinancialEvent.order_id == row.id)
                              .order_by(FinancialEvent.occurred_at)).all()
        returns = db.scalars(select(ReturnRequest).where(ReturnRequest.order_id == row.id)
                             .order_by(ReturnRequest.requested_at)).all()
        result.append({"id": row.id, "transaction_id": row.transaction_id, "source": "ONDC",
            "state": row.state, "internal_state": row.internal_state,
            "fulfillment_state": row.fulfillment_state, "amount": str(row.amount), "currency": row.currency,
            "fulfillment": row.fulfillment,
            "payment_status": row.payment.get("status", "NOT-PAID"),
            "items": [{"item_id": item.item_id, "variant_id": item.variant_id,
                       "quantity": item.quantity, "unit_price": str(item.unit_price),
                       "total_price": str(item.total_price)} for item in items],
            "history": [{"from_state": event.from_state, "to_state": event.to_state,
                         "fulfillment_state": event.fulfillment_state, "actor": event.actor,
                         "source": event.source, "occurred_at": event.occurred_at} for event in history],
            "financial_events": [{"event_type": event.event_type, "status": event.status,
                "currency": event.currency, "amount": str(event.amount),
                "transaction_reference": event.transaction_reference, "occurred_at": event.occurred_at}
                for event in finances],
            "returns": [{"request_id": item.request_id, "item_id": item.item_id, "quantity": item.quantity,
                         "reason_id": item.reason_id, "state": item.state,
                         "requested_at": item.requested_at, "decided_at": item.decided_at} for item in returns],
            "created_at": row.created_at})
    return result

class TransitionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: Literal["packed", "ready_for_pickup", "picked_up", "delivered", "fulfillment_failed"]
    idempotency_key: str = Field(min_length=1, max_length=255)

@router.post("/orders/{order_id}/transitions")
def transition_order(order_id: str, payload: TransitionInput, db: Session = Depends(get_db),
                     authenticated=Depends(require_admin)):
    order = db.scalar(select(ONDCOrder).where(ONDCOrder.id == order_id).with_for_update())
    if order is None: raise HTTPException(404, "Order not found")
    try:
        transition(db, order, payload.target, key=payload.idempotency_key,
                   actor="seller-admin", source="admin")
        db.commit()
    except ValueError as exc:
        db.rollback(); raise HTTPException(409, str(exc)) from None
    return {"id": order.id, "state": order.state, "internal_state": order.internal_state,
            "fulfillment_state": order.fulfillment_state}

class ReturnDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]

@router.post("/orders/{order_id}/returns/{request_id}/decision")
def decide_return(order_id: str, request_id: str, payload: ReturnDecision,
                  db: Session = Depends(get_db), authenticated=Depends(require_admin)):
    row = db.scalar(select(ReturnRequest).where(ReturnRequest.order_id == order_id,
                                                 ReturnRequest.request_id == request_id).with_for_update())
    if row is None: raise HTTPException(404, "Return request not found")
    target = "Return_Approved" if payload.decision == "approve" else "Return_Rejected"
    if row.state not in {"Return_Initiated", target}: raise HTTPException(409, "Return already decided")
    row.state, row.decided_at = target, row.decided_at or __import__("time").time()
    db.commit()
    return {"request_id": row.request_id, "state": row.state}

@router.get("/catalog-sync")
def catalog_sync(db: Session = Depends(get_db)):
    subscriptions = db.scalars(select(CatalogSubscription).order_by(CatalogSubscription.id)).all()
    jobs = db.scalars(select(CatalogPublicationJob).order_by(CatalogPublicationJob.id.desc()).limit(200)).all()
    return {"subscriptions": [{"id": row.id, "bap_id": row.bap_id, "status": row.status,
        "interval_seconds": row.interval_seconds, "cursor_at": row.cursor_at,
        "next_run_at": row.next_run_at} for row in subscriptions],
        "jobs": [{"id": row.id, "subscription_id": row.subscription_id, "status": row.status,
        "attempts": row.attempts, "next_attempt_at": row.next_attempt_at,
        "error": row.error, "window_start": row.window_start, "window_end": row.window_end} for row in jobs]}
