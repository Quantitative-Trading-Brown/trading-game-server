from flask_socketio import SocketIO

socketio = SocketIO(
    cors_allowed_origins=["https://simulator.qtab.site", "http://localhost:3000"],
    async_mode="threading",
)

def sid(request) -> str:
    if s := getattr(request, "sid", None):
        return s

    raise RuntimeError("No SID found in request.")
