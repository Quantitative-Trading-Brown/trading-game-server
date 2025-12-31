from .connections import blueprint as connections_blueprint
from .controller import blueprint as controller_blueprint
from .games import blueprint as game_blueprint
from .orders import blueprint as order_blueprint
from .query import blueprint as query_blueprint

blueprints = [
    connections_blueprint,
    controller_blueprint,
    game_blueprint,
    order_blueprint,
    query_blueprint,
]
