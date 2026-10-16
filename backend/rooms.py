import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile

import db
from security import check_password, current_user, hash_password

router = APIRouter(prefix="/api/rooms")

# room cover images live alongside shared files, under their own subfolder
ROOM_IMAGE_DIR = Path(os.environ.get("UPLOAD_DIR", Path(__file__).parent / "uploads")) / "rooms"
ROOM_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def public_room(row, user_id: str) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "memberLimit": row["member_limit"],
        "memberCount": row["member_count"],
        "isMember": bool(row["is_member"]),
        "full": row["member_count"] >= row["member_limit"],
        "hasPassword": bool(row["has_password"]),
        "isOwner": row["created_by"] == user_id,
        "lastVisitedAt": row["last_visited_at"],
        "imageUrl": row["image_url"],
    }


@router.get("")
async def rooms(user: dict = Depends(current_user)):
    return [public_room(r, user["id"]) for r in await db.list_rooms(user["id"])]


@router.post("", status_code=201)
async def create(
    name: str = Form(...),
    memberLimit: str = Form(...),
    password: str = Form(""),
    image: UploadFile | None = File(None),
    user: dict = Depends(current_user),
):
    name = name.strip()
    password = (password or "").strip()
    try:
        limit = int(memberLimit)
    except (TypeError, ValueError):
        raise HTTPException(400, "Member limit must be a number")

    if len(name) < 2 or len(name) > 40:
        raise HTTPException(400, "Room name must be 2 to 40 characters")
    if limit < 2 or limit > 500:
        raise HTTPException(400, "Member limit must be between 2 and 500")
    if password and len(password) < 4:
        raise HTTPException(400, "Room password must be at least 4 characters")

    image_url = None
    if image is not None and image.filename:
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(400, "Image must be a JPEG, PNG, WEBP or GIF")
        data = await image.read(MAX_IMAGE_SIZE + 1)
        if len(data) > MAX_IMAGE_SIZE:
            raise HTTPException(400, "Image too large (max 5 MB)")
        stored = secrets.token_hex(12) + os.path.splitext(image.filename)[1]
        (ROOM_IMAGE_DIR / stored).write_bytes(data)
        image_url = f"/uploads/rooms/{stored}"

    password_hash = await hash_password(password) if password else None
    now = datetime.now(timezone.utc).isoformat()
    room_id = await db.create_room(name, limit, password_hash, image_url, user["id"], now)
    await db.visit_room(room_id, user["id"], now)  # creator joins their own room

    room = await db.get_room(room_id)
    return public_room({
        **dict(room), "has_password": room["password_hash"] is not None,
        "member_count": 1, "is_member": 1, "last_visited_at": now,
    }, user["id"])


@router.post("/{room_id}/join")
async def join(room_id: int, data: dict = Body(default={}), user: dict = Depends(current_user)):
    room = await db.get_room(room_id)
    if not room:
        raise HTTPException(404, "Room not found")

    already_in = await db.is_member(room_id, user["id"])
    if not already_in:
        if room["password_hash"] is not None:
            password = str((data or {}).get("password", "") or "")
            if not password or not await check_password(password, room["password_hash"]):
                raise HTTPException(401, "Wrong room password")
        if await db.member_count(room_id) >= room["member_limit"]:
            raise HTTPException(409, "This room is full")

    now = datetime.now(timezone.utc).isoformat()
    await db.visit_room(room_id, user["id"], now)

    return public_room({
        **dict(room), "has_password": room["password_hash"] is not None,
        "member_count": await db.member_count(room_id), "is_member": 1, "last_visited_at": now,
    }, user["id"])
