import time, json

from app.services import *
from app.overseer import identity


def news(game_id, message):
    """Broadcast a message to all connected clients and save it in Valkey."""
    news_key = f"game:{game_id}:news"

    entry = {
        "timestamp": time.strftime("%H:%M:%S", time.localtime()),
        "message": "[news] " + message,
    }

    r.lpush(news_key, json.dumps(entry))
    r.ltrim(news_key, 0, 99)

    # Broadcast to admins and players
    socketio.emit(
        "news", [entry["timestamp"], entry["message"]], namespace="/admin", to=game_id
    )
    socketio.emit(
        "news", [entry["timestamp"], entry["message"]], namespace="/player", to=game_id
    )
