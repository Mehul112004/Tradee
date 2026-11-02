"""Native-candle C08 observation contract, distinct from legacy C02 CandidateSpec.

The quick adapter and dedicated diagnostic research runner share PilotEngine.
These observations are not automatically C09 intents or C12 releases.
"""
from tradee.pilots.contracts import FAMILIES,MODES,PilotConfig
from tradee.pilots.engine import PilotEngine
from tradee.pilots.execution import qualify


def catalog():
    return dict(families=list(FAMILIES),modes=list(MODES),timeframe='15m',context_timeframe='1h',
                symbols=['BTCUSDT','ETHUSDT'],default_config=PilotConfig().document(),
                contract='native structural observation',live_approved=False)


__all__=['PilotEngine','PilotConfig','qualify','catalog']
