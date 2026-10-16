import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

import db
from security import current_user

router = APIRouter(prefix="/api/rooms")

UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", Path(__file__).parent / "uploads"))
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_SIZE = 10 * 1024 * 1024  # 10 MB


def public(row) -> dict:
    """Turn a database row into JSON the frontend understands."""
    file = None
    if row["file_url"]:
        file = {
            "url": row["file_url"],
            "name": row["file_name"],
            "size": row["file_size"],
            "mimetype": row["file_mimetype"],
        }
    return {
        "_id": str(row["id"]),
        "room": row["room_id"],
        "user": row["user_id"],
        "username": row["username"],
        "text": row["text"],
        "file": file,
        "createdAt": row["created_at"],
    }


async def save_message(room_id: int, user_id: str, username: str, text: str = "", file: dict | None = None) -> dict:
    created_at = datetime.now(timezone.utc).isoformat()
    new_id = await db.add_message(room_id, user_id, username, text, file, created_at)
    return public({
        "id": new_id, "room_id": room_id, "user_id": user_id, "username": username, "text": text,
        "file_url": (file or {}).get("url"), "file_name": (file or {}).get("name"),
        "file_size": (file or {}).get("size"), "file_mimetype": (file or {}).get("mimetype"),
        "created_at": created_at,
    })


async def require_membership(room_id: int, user_id: str):
    room = await db.get_room(room_id)
    if not room:
        raise HTTPException(404, "Room not found")
    if not await db.is_member(room_id, user_id):
        raise HTTPException(403, "Join the room first")
    return room


# chat history for one room (last 100 messages)
@router.get("/{room_id}/messages")
async def history(room_id: int, user: dict = Depends(current_user)):
    await require_membership(room_id, user["id"])
    return [public(r) for r in await db.recent_messages(room_id, 100)]


# file sharing inside one room
@router.post("/{room_id}/files", status_code=201)
async def upload(room_id: int, file: UploadFile = File(...), user: dict = Depends(current_user)):
    from main import sio  # imported here to avoid a circular import

    await require_membership(room_id, user["id"])

    data = await file.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise HTTPException(400, "File too large (max 10 MB)")

    # random name on disk, so files can't be guessed or overwritten
    stored = secrets.token_hex(12) + os.path.splitext(file.filename or "")[1]
    (UPLOAD_DIR / stored).write_bytes(data)

    msg = await save_message(
        room_id,
        user["id"],
        user["username"],
        file={
            "url": f"/uploads/{stored}",
            "name": file.filename or "file",
            "size": len(data),
            "mimetype": file.content_type or "application/octet-stream",
        },
    )
    await sio.emit("message", msg, room=f"room:{room_id}")
    return msg
