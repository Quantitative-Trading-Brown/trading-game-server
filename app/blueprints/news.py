from flask import Blueprint, request

from app.services import *
from app.overseer import identity
from app.communication import broadcast

blueprint = Blueprint("news", __name__)

@socketio.on("news", namespace="/admin")
def admin_broadcast(message):
    game_id, _ = identity.identify(sid(request))
    broadcast.news(game_id, message)
