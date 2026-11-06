from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..auth.users import check_password, create_user, current_user, end_session, find_user, new_session
from ..schemas.models import LoginIn, RegisterIn, SessionOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _out(u: dict) -> UserOut:
    return UserOut(id=u["id"], email=u["email"], name=u.get("name"), persona=u.get("persona"), settings=u.get("settings") or {})


@router.post("/register", response_model=SessionOut)
def register(body: RegisterIn, response: Response):
    if find_user(body.email):
        raise HTTPException(409, "email already registered")
    u = create_user(body.email, body.password, body.name, body.persona)
    from .settings import seed_searches

    seed_searches(u)
    tok = new_session(u["id"])
    response.set_cookie("gigbid_session", tok, httponly=True, samesite="lax", max_age=14 * 86400)
    return SessionOut(token=tok, user=_out(u))


@router.post("/login", response_model=SessionOut)
def login(body: LoginIn, response: Response):
    u = find_user(body.email)
    if not u or not check_password(body.password, u["password_hash"]):
        raise HTTPException(401, "wrong email or password")
    tok = new_session(u["id"])
    response.set_cookie("gigbid_session", tok, httponly=True, samesite="lax", max_age=14 * 86400)
    return SessionOut(token=tok, user=_out(u))


@router.post("/logout")
def logout(request: Request, response: Response):
    tok = request.cookies.get("gigbid_session") or request.headers.get("authorization", "")[7:]
    if tok:
        end_session(tok)
    response.delete_cookie("gigbid_session")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(current_user)):
    return _out(user)
