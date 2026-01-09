from .connections import blueprint as connections_blueprint
from .controls import blueprint as controller_blueprint
from .news import blueprint as news_blueprint
from .trading import blueprint as trading_blueprint
from .queries import blueprint as query_blueprint

from .overseer import blueprint as overseer_blueprint

blueprints = [
    connections_blueprint,
    controller_blueprint,
    news_blueprint,
    trading_blueprint,
    query_blueprint,
    overseer_blueprint,
]
