from tradee.observations import ObservationStore
from .engine import ContextEngine


class ContextStore(ObservationStore):
    APP_ID = 0x54524434
    ENGINE = ContextEngine
    COMPONENT = 'C04'

    def __init__(self, path='data/c04.sqlite3', **kwargs):
        super().__init__(path, **kwargs)
