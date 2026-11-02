"""Bounded, checksum-verified Binance archive acquisition; never reads reserved months."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import time
from urllib.request import Request
import zipfile

from tradee.c01 import ValidationError
from tradee.c01.provider import verified_urlopen

ROOT = 'https://data.binance.vision/data/futures/um/monthly/'


def months(start, end):
    year, month = map(int, start[:7].split('-'))
    while f'{year:04d}-{month:02d}' < end[:7]:
        yield f'{year:04d}-{month:02d}'
        year, month = (year+1, 1) if month == 12 else (year, month+1)


def get(url, limit):
    for attempt in range(3):
        try:
            with verified_urlopen(Request(url, headers={'User-Agent':'Tradee-Research/1'}), timeout=30) as r:
                data = r.read(limit+1)
            if len(data) > limit: raise ValidationError('Archive response exceeds declared budget')
            return data
        except Exception:
            if attempt == 2: raise
            time.sleep(.5*(attempt+1))


def acquire(directory, symbol, interval, month):
    if symbol not in ('BTCUSDT','ETHUSDT') or interval not in ('1m','15m','1h','fundingRate'):
        raise ValidationError('Unsupported pilot archive scope')
    name=f'{symbol}-{interval}-{month}.zip'
    rel=f'fundingRate/{symbol}/{name}' if interval=='fundingRate' else f'klines/{symbol}/{interval}/{name}'
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    path=directory/name; meta=directory/(name+'.json')
    if path.exists() and meta.exists():
        saved=json.loads(meta.read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=saved['sha256']: raise ValidationError('Cached archive checksum mismatch')
        return saved
    checksum=get(ROOT+rel+'.CHECKSUM',1024).decode().split()
    if len(checksum)!=2 or checksum[1]!=name or len(checksum[0])!=64: raise ValidationError('Invalid public checksum')
    data=get(ROOT+rel,128*1024*1024)
    digest=hashlib.sha256(data).hexdigest()
    if digest!=checksum[0]: raise ValidationError('Public archive checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        if len(z.infolist())!=1 or z.infolist()[0].file_size>512*1024*1024: raise ValidationError('Unsafe archive budget')
    tmp=path.with_suffix('.part'); tmp.write_bytes(data); tmp.replace(path)
    saved=dict(url=ROOT+rel,sha256=digest,bytes=len(data),received_ms=int(time.time()*1000))
    meta.write_text(json.dumps(saved,sort_keys=True,indent=2)+'\n')
    return saved


def rows(path):
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos)!=1 or infos[0].file_size>512*1024*1024: raise ValidationError('Unsafe archive')
        with z.open(infos[0]) as f:
            for row in csv.reader(io.TextIOWrapper(f)):
                if not row or not row[0].isdigit(): continue
                if len(row)<8: raise ValidationError('Malformed archive row')
                yield row


def candles(directory, symbol, interval, start, end):
    size={'1m':60000,'15m':900000,'1h':3600000}[interval]
    previous=None
    for month in months(start,end):
        path=Path(directory)/f'{symbol}-{interval}-{month}.zip'
        for row in rows(path):
            t=int(row[0])
            if t>10**14: t//=1000
            if t%size or previous is not None and t<=previous: raise ValidationError('Unsorted/misaligned archive')
            previous=t
            yield dict(open_ms=t,open=row[1],high=row[2],low=row[3],close=row[4],quote_volume=row[7],available_ms=t+size)


def main():
    p=argparse.ArgumentParser(); p.add_argument('--protocol',default='configs/pilot_research_v1.json')
    p.add_argument('--directory',default='data/pilot-research/archives'); p.add_argument('--minutes',action='store_true')
    a=p.parse_args(); protocol=json.loads(Path(a.protocol).read_text())
    intervals=['15m','fundingRate']+(['1m'] if a.minutes else [])
    tasks=[(s,i,m) for s in protocol['symbols'] for i in intervals for m in months(protocol['warmup_start'],protocol['development_end'])]
    failures=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(acquire,a.directory,*t):t for t in tasks}
        for n,f in enumerate(as_completed(jobs),1):
            try: f.result()
            except Exception as e: failures.append(dict(task=jobs[f],error=str(e)))
            if n%10==0: print(json.dumps(dict(completed=n,total=len(tasks),failures=len(failures))),flush=True)
    Path(a.directory).joinpath('acquisition.json').write_text(json.dumps(dict(protocol=protocol,tasks=len(tasks),failures=failures),indent=2)+'\n')
    print(json.dumps(dict(tasks=len(tasks),failures=failures)),flush=True)
    if failures: raise SystemExit(2)


if __name__=='__main__': main()
