from flask import Blueprint, request
from typing import Awaitable, Any
import json

from ..utils import helpers
from ..utils.services import *

snapshot_manager = Blueprint("snapshot_manager", __name__)


@socketio.on("snapshot", namespace="/admin")
def admin_snapshot():
    game_id, _ = helpers.identify(sid(request))

    socketio.emit(
        "snapshot", helpers.make_snapshot(game_id), namespace="/admin", to=sid(request)
    )


@socketio.on("snapshot", namespace="/player")
def player_snapshot():
    game_id, player_id = helpers.identify(sid(request))

    socketio.emit(
        "snapshot",
        helpers.make_snapshot(game_id, player_id),
        namespace="/player",
        to=sid(request),
    )
