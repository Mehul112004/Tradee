from tradee.observations import register_commands, execute_command
from .contracts import ContextConfig
from .engine import ContextEngine
from .store import ContextStore


def register(sub):
    register_commands(sub, 'context', 'c04', 'C04 causal market-context observations')


def execute(args):
    return execute_command(args, ContextConfig, ContextStore, ContextEngine)
