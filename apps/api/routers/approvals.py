"""Approvals: the only path by which anything leaves GigBid. A decision is persisted first (status 'decided'),
then the interrupted graph thread is resumed by the worker; a crash in between is recovered on restart."""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update

from core.db import approvals, engine, row_dict

from .. import dispatch
from ..auth.users import current_user
from ..schemas.models import ApprovalOut, DecisionIn, RunRef

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalOut])
def pending(kind: str | None = None, user: dict = Depends(current_user)):
    with engine().begin() as c:
        stmt = select(approvals).where(approvals.c.user_id == user["id"], approvals.c.status == "pending")
        if kind:
            stmt = stmt.where(approvals.c.kind == kind)
        return [ApprovalOut(**row_dict(r)) for r in c.execute(stmt.order_by(approvals.c.created_at.desc()))]


@router.get("/{approval_id}", response_model=ApprovalOut)
def get_one(approval_id: str, user: dict = Depends(current_user)):
    with engine().begin() as c:
        r = c.execute(select(approvals).where(approvals.c.id == approval_id, approvals.c.user_id == user["id"])).first()
    if not r:
        raise HTTPException(404, "approval not found")
    return ApprovalOut(**row_dict(r))


@router.post("/{approval_id}/decide", response_model=RunRef)
async def decide(approval_id: str, body: DecisionIn, user: dict = Depends(current_user)):
    if body.action == "reject" and not (body.reason or "").strip():
        raise HTTPException(422, "a reason is required to reject")
    if body.action == "edit" and not (body.cover_letter or body.body):
        raise HTTPException(422, "edited text is required")
    decision = body.model_dump(exclude_none=True) | {"by": user["id"]}
    with engine().begin() as c:
        res = c.execute(update(approvals).where(approvals.c.id == approval_id, approvals.c.user_id == user["id"],
                                                approvals.c.status == "pending").values(status="decided", decision=decision,
                                                                                        decided_at=time.time()))
        row = c.execute(select(approvals).where(approvals.c.id == approval_id)).first()
    if res.rowcount == 0:
        raise HTTPException(409, "already decided")
    await dispatch.enqueue("resume", user_id=user["id"], thread_id=row.thread_id, decision=decision)
    return RunRef(status="resuming")
