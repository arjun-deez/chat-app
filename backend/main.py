import os

import jwt
import socketio
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

load_dotenv()

import auth  # noqa: E402
import chat  # noqa: E402
import db  # noqa: E402
import rooms  # noqa: E402
from security import read_token  # noqa: E402

CLIENT_URL = os.environ.get("CLIENT_URL", "http://localhost:5173")

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=[CLIENT_URL], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def on_startup():
    await db.seed_dummy_rooms()


# the frontend reads {"error": "..."}, so return errors in that shape
@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def bad_request(request: Request, exc: RequestValidationError):
    return JSONResponse({"error": "Invalid request"}, status_code=400)


@app.get("/")
async def root():
    return "Chat API is running"


app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(chat.router)
app.mount("/uploads", StaticFiles(directory=chat.UPLOAD_DIR), name="uploads")

# ---- real-time chat ----
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=[CLIENT_URL])


@sio.event
async def connect(sid, environ, auth_data):
    # only logged-in users can connect
    try:
        user = read_token((auth_data or {}).get("token", ""))
    except jwt.PyJWTError:
        raise socketio.exceptions.ConnectionRefusedError("Unauthorized")
    await sio.save_session(sid, {"id": user["id"], "username": user["username"], "room": None})


@sio.on("join_room")
async def on_join_room(sid, room_id):
    """A user opened a room's chat screen. Only members may listen in."""
    session = await sio.get_session(sid)
    if not await db.is_member(int(room_id), session["id"]):
        return
    if session.get("room"):
        await sio.leave_room(sid, f"room:{session['room']}")
    await sio.enter_room(sid, f"room:{room_id}")
    session["room"] = int(room_id)
    await sio.save_session(sid, session)


@sio.on("leave_room")
async def on_leave_room(sid):
    session = await sio.get_session(sid)
    if session.get("room"):
        await sio.leave_room(sid, f"room:{session['room']}")
        session["room"] = None
        await sio.save_session(sid, session)


@sio.on("message")
async def on_message(sid, text):
    text = str(text or "").strip()[:2000]
    session = await sio.get_session(sid)
    room_id = session.get("room")
    if not text or not room_id:
        return
    msg = await chat.save_message(room_id, session["id"], session["username"], text=text)
    await sio.emit("message", msg, room=f"room:{room_id}")


# run this one:  uvicorn main:asgi
asgi = socketio.ASGIApp(sio, other_asgi_app=app)
