from .sinewave import SinewaveBot
from .flat import FlatBot
from .timeseries import TimeSeriesBot

# Mapping strategy names to classes
bots = {
    "sinewave": SinewaveBot,
    "flat": FlatBot,
    "ts": TimeSeriesBot,
}
