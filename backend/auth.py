import sqlite3

from fastapi import APIRouter, Body, HTTPException

import db
from security import check_password, hash_password, make_token

router = APIRouter(prefix="/api/auth")


def _clean(data: dict):
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    return username, password


@router.post("/signup", status_code=201)
async def signup(data: dict = Body(...)):
    username, password = _clean(data)
    if len(username) < 3 or len(username) > 20:
        raise HTTPException(400, "Username must be 3 to 20 characters")
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if len(password.encode()) > 72:
        raise HTTPException(400, "Password is too long (max 72 bytes)")

    try:
        new_id = await db.create_user(username, await hash_password(password))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Username already taken")

    user_id = str(new_id)
    return {"token": make_token(user_id, username), "user": {"id": user_id, "username": username}}


@router.post("/login")
async def login(data: dict = Body(...)):
    username, password = _clean(data)
    user = await db.get_user(username)
    # same message for both failures so attackers can't tell which one was wrong
    if not user or len(password.encode()) > 72 or not await check_password(password, user["password"]):
        raise HTTPException(401, "Wrong username or password")

    user_id = str(user["id"])
    return {"token": make_token(user_id, user["username"]), "user": {"id": user_id, "username": user["username"]}}
