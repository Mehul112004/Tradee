"""Asynchronous public calendar/time preparation; no account or order endpoints."""
import json
from pathlib import Path
import threading
from urllib.request import Request

from tradee.c01.provider import verified_urlopen
from tradee.pilots.calendar import CalendarCache
from tradee.pilots.contracts import DAY


class PilotSources:
    def __init__(self,path,clock):
        self.calendar=CalendarCache(path,clock=clock); self.clock=clock
        self.offset=None; self.offset_at=0; self.calendar_value=None
        self.clock_observation=None
        self.thread=None; self.next_ms=0

    def prepare(self,now):
        if self.thread and self.thread.is_alive() or now<self.next_ms: return
        self.next_ms=now+300000
        def work():
            try:
                before=int(self.clock()*1000)
                with verified_urlopen(Request('https://fapi.binance.com/fapi/v1/time'),timeout=5) as response:
                    data=json.loads(response.read(1024))
                after=int(self.clock()*1000); server=data['serverTime']
                offset=server-(before+after)//2
                if type(server) is int and 0<=after-before<=1000 and abs(offset)+(after-before)/2<=1000:
                    self.offset,self.offset_at=offset,after
                    self.clock_observation=dict(source='https://fapi.binance.com/fapi/v1/time',server_ms=server,request_ms=before,received_ms=after)
                else: self.offset=None
            except Exception: self.offset=None
            self.calendar_value=self.calendar.view(int(self.clock()*1000))
        self.thread=threading.Thread(target=work,name='tradee-pilot-public-context',daemon=True); self.thread.start()

    def evidence(self,feed,plan,metadata,now):
        self.prepare(now)
        value=feed.execution_evidence(plan['symbol'],plan['end_ms']) if feed and hasattr(feed,'execution_evidence') else {}
        return dict(value,metadata=metadata,calendar=self.calendar_value if self.calendar_value and now-self.calendar_value['refreshed_ms']<=DAY else None,
                    clock_observation=self.clock_observation,
                    clock_offset_ms=self.offset if now-self.offset_at<300000 else None)

    def status(self,now):
        return dict(calendar='ready' if self.calendar_value and now-self.calendar_value['refreshed_ms']<=DAY else 'unavailable or preparing; strict alerts blocked',
                    clock='ready' if self.offset is not None and now-self.offset_at<300000 else 'unverified; strict alerts blocked')
