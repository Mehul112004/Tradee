"""Independent range-breakout and EMA pullback-continuation hypotheses."""
from .contracts import StrategySpec, CandidateConfig, CandidateSpec, CandidateRecord
from .engine import CandidateEngine
from .store import CandidateStore

__all__=['StrategySpec','CandidateConfig','CandidateSpec','CandidateRecord','CandidateEngine','CandidateStore']
