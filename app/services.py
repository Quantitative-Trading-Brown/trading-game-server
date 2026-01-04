from typing import Awaitable, Any

from flask import current_app
from flask_socketio import SocketIO
import valkey

r = valkey.Valkey(host="localhost", port=6379, db=0, decode_responses=True)

socketio = SocketIO(async_mode="threading")


def extract(value: Any) -> Any:
    if value is None:
        raise RuntimeError("No value found.")
    if isinstance(value, Awaitable):
        raise RuntimeError("Async operation not supported here.")
    return value


def sid(request) -> str:
    if s := getattr(request, "sid", None):
        return s

    raise RuntimeError("No SID found in request.")
