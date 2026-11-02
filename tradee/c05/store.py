from tradee.observations import ObservationStore
from .engine import StructureEngine


class StructureStore(ObservationStore):
    APP_ID = 0x54524435
    ENGINE = StructureEngine
    COMPONENT = 'C05'

    def __init__(self, path='data/c05.sqlite3', **kwargs):
        super().__init__(path, **kwargs)
