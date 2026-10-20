"""Frozen paper-notification runtime contracts; actionable live mode is unavailable."""
from dataclasses import dataclass
import re
from tradee.c01 import ValidationError
from tradee.c02.domain import integer
from tradee.c13.contracts import fields,text


@dataclass(frozen=True)
class RuntimeConfig:
    version: int = 1
    mode: str = 'shadow'
    bot_id: int | None = None
    chat_id: int | None = None
    source_settle_ms: int = 250
    max_notice_age_ms: int = 10000
    max_cycle_age_ms: int = 5000
    http_timeout_ms: int = 3000
    lease_ms: int = 15000
    chat_interval_ms: int = 3500
    bot_interval_ms: int = 100
    max_attempts: int = 3
    retry_base_ms: int = 1000
    max_events: int = 50000
    max_candidates: int = 1000
    max_artifacts: int = 100000
    max_cycles: int = 10000
    max_cycle_bytes: int = 50000000
    max_session_ms: int = 86400000

    def __post_init__(self):
        if type(self.version) is not int or self.version!=1 or self.mode not in ('shadow','paper_test'): raise ValidationError('C14 supports shadow/paper_test only; live promotion is not implemented')
        for k in self.__dataclass_fields__:
            if k in ('version','mode','bot_id','chat_id'): continue
            integer(getattr(self,k),k)
            if k!='source_settle_ms' and not getattr(self,k): raise ValidationError('Positive bounded runtime settings required')
        caps=dict(source_settle_ms=60000,max_notice_age_ms=60000,max_cycle_age_ms=30000,http_timeout_ms=10000,lease_ms=120000,
            chat_interval_ms=3600000,bot_interval_ms=60000,max_attempts=10,retry_base_ms=60000,max_events=250000,max_candidates=10000,max_artifacts=500000,
            max_cycles=100000,max_cycle_bytes=50000000,max_session_ms=604800000)
        if any(getattr(self,k)>v for k,v in caps.items()) or self.lease_ms<=self.http_timeout_ms or self.chat_interval_ms<3000 or self.bot_interval_ms<40: raise ValidationError('Unsupported runtime bounds, lease or Telegram throttle')
        if self.mode=='paper_test':
            integer(self.bot_id,'Telegram bot id')
            if not self.bot_id or type(self.chat_id) is not int or not self.chat_id or abs(self.chat_id)>10**16: raise ValidationError('Explicit numeric paper-test bot/chat destination required')
        elif self.bot_id is not None or self.chat_id is not None: raise ValidationError('Shadow mode has no Telegram destination')

    def document(self): return {k:getattr(self,k) for k in self.__dataclass_fields__}
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)


@dataclass(frozen=True)
class SessionSpec:
    name: str
    start_ms: int
    end_ms: int
    warmup_start_ms: int
    tail_ms: int
    runtime: dict | None = None

    def __post_init__(self):
        if not isinstance(self.name,str) or not re.fullmatch('[a-z][a-z0-9_-]{0,63}',self.name): raise ValidationError('Short lowercase C14 session name required')
        for k in ('start_ms','end_ms','warmup_start_ms','tail_ms'): integer(getattr(self,k),k)
        if self.runtime is not None and not isinstance(self.runtime,dict): raise ValidationError('Explicit runtime object required')
        cfg=RuntimeConfig.from_dict({} if self.runtime is None else self.runtime)
        if (not self.warmup_start_ms<self.start_ms<self.end_ms or any(getattr(self,k)%60000 for k in ('start_ms','end_ms','warmup_start_ms','tail_ms'))
                or self.end_ms-self.start_ms>cfg.max_session_ms or self.start_ms-self.warmup_start_ms>cfg.max_session_ms or self.tail_ms>cfg.max_session_ms):
            raise ValidationError('Ordered minute-aligned bounded warm-up, session and tail required')
        object.__setattr__(self,'runtime',cfg)
    def document(self): return dict(name=self.name,start_ms=self.start_ms,end_ms=self.end_ms,warmup_start_ms=self.warmup_start_ms,tail_ms=self.tail_ms,runtime=self.runtime.document())
    @property
    def tail_end_ms(self): return self.end_ms+self.tail_ms
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    reason: str
    message_id: int | None = None
    retry_after_ms: int = 0

    def __post_init__(self):
        if self.status not in ('sent','retry','failed','ambiguous') or not isinstance(self.reason,str) or not re.fullmatch('[a-z][a-z0-9_]{0,95}',self.reason): raise ValidationError('Redacted structured delivery result required')
        integer(self.retry_after_ms,'retry delay')
        if self.retry_after_ms>86400000: raise ValidationError('Unsupported Telegram retry delay')
        if self.status=='sent':
            integer(self.message_id,'message id')
            if not self.message_id: raise ValidationError('Telegram acceptance requires a positive message id')
        elif self.message_id is not None: raise ValidationError('Unconfirmed delivery cannot claim a message id')
    def document(self): return {k:getattr(self,k) for k in self.__dataclass_fields__}
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)
