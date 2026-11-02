from tradee.observations import register_commands, execute_command
from .contracts import StructureConfig
from .engine import StructureEngine
from .store import StructureStore


def register(sub):
    register_commands(sub, 'structure', 'c05', 'C05 causal price-level observations')


def execute(args):
    return execute_command(args, StructureConfig, StructureStore, StructureEngine)
