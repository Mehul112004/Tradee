"""Versioned official calendar coverage; inaccessible/stale sources fail closed."""
from datetime import datetime,timedelta,timezone
from html import unescape
import hashlib
import json
from pathlib import Path
import re
import time
from zoneinfo import ZoneInfo

from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from .archive import get
from .contracts import DAY

NY=ZoneInfo('America/New_York')


def timestamp(date, time='00:00', zone=NY):
    return int(datetime.fromisoformat(date+'T'+time).replace(tzinfo=zone).timestamp()*1000)


def blackout(date, kind, known_ms, time=None):
    if time is None:
        local=datetime.fromisoformat(date).replace(tzinfo=NY)
        start=int(local.timestamp()*1000); end=int((local+timedelta(days=1)).timestamp()*1000)
    else:
        t=timestamp(date,time); start=t-1800000; end=t+(3600000 if kind=='fomc' else 1800000)
    return dict(kind=kind,start_ms=start,end_ms=end,known_ms=known_ms)


def reconstructed(document):
    result=[]
    for kind in ('cpi','employment','fomc'):
        for year,dates in document[kind].items():
            for date in dates:
                result.append(blackout(year+'-'+date,kind,0,None if kind=='fomc' else document['bls_time']))
    return sorted(result,key=lambda e:e['start_ms'])


def plain(html): return ' '.join(unescape(re.sub('<[^>]*>',' ',html)).split())


def parse_bls(html,year,known):
    txt=plain(html)
    pattern=r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+('+str(year)+r')\s+(\d{1,2}:\d{2}\s+[AP]M)\s+(Consumer Price Index|Employment Situation)\s+for\b'
    events=[]
    for month,day,y,tm,title in re.findall(pattern,txt):
        date=datetime.strptime(f'{month} {day} {y}','%B %d %Y').date().isoformat()
        clock=datetime.strptime(tm,'%I:%M %p').strftime('%H:%M')
        events.append(blackout(date,'cpi' if title=='Consumer Price Index' else 'employment',known,clock))
    events=list({(e['kind'],e['start_ms']):e for e in events}.values())
    if any(sum(e['kind']==k for e in events)<10 for k in ('cpi','employment')): raise ValidationError('Official BLS annual calendar has insufficient verified coverage')
    return sorted(events,key=lambda e:e['start_ms'])


def parse_fed(html,year,known):
    parts=re.split(r'(\d{4}) FOMC Meetings',html)
    segment=next((parts[i+1] for i in range(1,len(parts)-1,2) if int(parts[i])==year),None)
    if segment is None: raise ValidationError('Official FOMC year missing')
    pairs=re.findall(r'fomc-meeting__month[^>]*>(.*?)</div>\s*<div[^>]*fomc-meeting__date[^>]*>(.*?)</div>',segment,re.S)
    events=[]
    for month,days in pairs:
        month=plain(month).split('/')[-1]; numbers=re.findall(r'\d+',plain(days))
        if not numbers: raise ValidationError('Unknown FOMC date')
        try: m=datetime.strptime(month,'%B').month
        except ValueError: m=datetime.strptime(month,'%b').month
        date=datetime(year,m,int(numbers[-1])).date().isoformat()
        # Date verified, time not verified by this calendar page: conservative full local date.
        events.append(blackout(date,'fomc',known))
    if len(events)<8: raise ValidationError('Official FOMC annual coverage incomplete')
    return events


class CalendarCache:
    def __init__(self,path,clock=time.time): self.path=Path(path); self.retry_after_ms=0; self.clock=clock; self.last_error=''

    def view(self,now):
        try:
            if self.path.exists():
                saved=json.loads(self.path.read_text())
                if saved.get('refreshed_ms',0)<=now<saved.get('refreshed_ms',0)+DAY and saved.get('coverage_end_ms',0)>now+4*3600000 and saved.get('source_receipts') and saved.get('blackouts'): return saved
        except (ValueError,OSError,TypeError): pass
        if now<self.retry_after_ms: return None
        self.retry_after_ms=now+3600000
        year=datetime.fromtimestamp(now/1000,timezone.utc).year
        try:
            urls=[f'https://www.bls.gov/schedule/{year}/','https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm']
            bodies=[]; receipts=[]
            for url in urls:
                raw=get(url,3000000); received=int(self.clock()*1000)
                bodies.append(raw.decode()); receipts.append(dict(url=url,received_ms=received,sha256=hashlib.sha256(raw).hexdigest()))
            known=max(r['received_ms'] for r in receipts)
            if known<now: raise ValidationError('Calendar receipt clock moved backwards')
            events=parse_bls(bodies[0],year,known)+parse_fed(bodies[1],year,known)
            value=dict(sources=['bls_cpi','bls_employment','fomc'],refreshed_ms=known,
                coverage_start_ms=timestamp(f'{year}-01-01'),coverage_end_ms=timestamp(f'{year+1}-01-01'),blackouts=events,
                source_urls=urls,source_receipts=receipts)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            for body,receipt in zip(bodies,receipts):
                source=self.path.with_name(f"calendar-source-{receipt['sha256']}.html")
                if source.exists() and hashlib.sha256(source.read_bytes()).hexdigest()!=receipt['sha256']: raise ValidationError('Calendar raw evidence hash mismatch')
                if not source.exists(): source.write_bytes(body.encode())
            version=self.path.with_name(f'{self.path.stem}-{fingerprint(value)}.json')
            version.write_text(json.dumps(value,sort_keys=True)+'\n')
            tmp=self.path.with_suffix('.part'); tmp.write_text(json.dumps(value,sort_keys=True)+'\n'); tmp.replace(self.path)
            return value
        except Exception as exc:
            self.last_error=type(exc).__name__+': '+str(exc)[:200]
            return None
