"""Regenerate external reference fixture, without importing Tradee calculations.

Requires TA-Lib 0.6.8 and NumPy 2.4.1 in the supplied temporary oracle directory.
The ordinary suite reads committed JSON and needs neither library.
"""
import argparse
import json
import math
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(); p.add_argument('--oracle-path',required=True,type=Path)
    p.add_argument('--output',default='tests/fixtures/c03/talib_0_6_8.json',type=Path)
    args=p.parse_args(); sys.path.insert(0,str(args.oracle_path))
    import numpy as np
    import talib
    if (talib.__version__,np.__version__)!=('0.6.8','2.4.1'):
        raise RuntimeError('Oracle versions do not match the pinned fixture contract')
    talib.set_compatibility(0)
    for name in ('EMA','ATR','RSI'): talib.set_unstable_period(name,0)
    closes=[100+((i*17)%31-15)/10+i/100 for i in range(100)]
    highs=[c+1+(i%3)/10 for i,c in enumerate(closes)]
    lows=[c-1-(i%2)/10 for i,c in enumerate(closes)]
    c,h,l=map(lambda values:np.asarray(values,dtype=np.float64),(closes,highs,lows))
    upper,middle,lower=talib.BBANDS(c,timeperiod=20,nbdevup=2,nbdevdn=2,matype=0)
    results=dict(ema20=talib.EMA(c,timeperiod=20),ema50=talib.EMA(c,timeperiod=50),
        atr14=talib.ATR(h,l,c,timeperiod=14),rsi14=talib.RSI(c,timeperiod=14),
        bb20_upper=upper,bb20_middle=middle,bb20_lower=lower)
    doc=dict(provenance=dict(generator='scripts/generate_c03_oracle.py',wrapper=talib.__version__,
        c_library=talib.__ta_version__.decode(),numpy=np.__version__,compatibility=0,unstable_period=0,
        flat_rsi='Not compared: Tradee deliberately uses neutral 50, TA-Lib uses 0',
        tolerance=dict(absolute=1e-12,relative=1e-10)),
        input=dict(close=closes,high=highs,low=lows),
        expected={k:[None if math.isnan(float(x)) else float(x) for x in v] for k,v in results.items()})
    args.output.write_text(json.dumps(doc,indent=2,allow_nan=False)+'\n')
    print(json.dumps(doc['provenance'],indent=2))


if __name__=='__main__': main()
