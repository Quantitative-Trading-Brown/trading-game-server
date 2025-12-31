from ..services import *

def set_state(game_id: str, state: int) -> None:
    # Update in Redis backend
    r.set(f"game:{game_id}:state", state)

    # Notify all clients about the state change
    socketio.emit("gamestate_update", state, namespace="/admin", to=game_id)
    socketio.emit("gamestate_update", state, namespace="/player", to=game_id)
