from flask_socketio import SocketIO
import valkey

socketio = SocketIO(
    cors_allowed_origins=["https://simulator.qtab.site", "http://localhost:3000"],
    async_mode="threading",
)
sid = lambda x : getattr(x, "sid", None)

r = valkey.Valkey(host="localhost", port=6379, db=0, decode_responses=True)
