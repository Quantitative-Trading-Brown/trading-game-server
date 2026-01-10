from flask import Blueprint, request

from app.services import *
from app.overseer import identity
from app.state import states


blueprint = Blueprint("controls", __name__)


@socketio.on("startgame", namespace="/admin")
def start_game(preset, allow_join):
    game_id, _ = identity.identify(sid(request))
    states.setup_to_live(game_id, preset, allow_join)


@socketio.on("endgame", namespace="/admin")
def end_game():
    game_id, _ = identity.identify(sid(request))
    states.live_to_settlement(game_id)


@socketio.on("rankgame", namespace="/admin")
def rank_game(true_prices={}):
    game_id, _ = identity.identify(sid(request))
    states.settlement_to_results(game_id, true_prices)
