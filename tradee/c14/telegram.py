"""Minimal fixed-host TLS Telegram sender. Unknown HTTP outcomes never auto-retry."""
import json
import os
import re
import socket
import ssl
from urllib import request,error
from tradee.c01 import ValidationError
from .contracts import DeliveryResult


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


class TelegramTransport:
    def __init__(self,token,bot_id,opener=None):
        if not isinstance(token,str) or not re.fullmatch(r'[1-9][0-9]{3,19}:[A-Za-z0-9_-]{20,100}',token) or int(token.split(':')[0])!=bot_id: raise ValidationError('Configured Telegram bot credential is missing or mismatched')
        self._token=token; self.bot_id=bot_id
        context=ssl.create_default_context()
        if os.sys.platform=='darwin' and not os.environ.get('SSL_CERT_FILE') and os.path.isfile('/etc/ssl/cert.pem'): context.load_verify_locations(cafile='/etc/ssl/cert.pem')
        self.opener=opener or request.build_opener(request.ProxyHandler({}),NoRedirect(),request.HTTPSHandler(context=context))
    def __repr__(self): return f'TelegramTransport(bot_id={self.bot_id}, token=<redacted>)'

    def send(self,chat_id,text,timeout_ms):
        if type(chat_id) is not int or not chat_id or not isinstance(text,str) or not 1<=len(text)<=4096 or type(timeout_ms) is not int or timeout_ms<=0: raise ValidationError('Bounded plain Telegram paper message and timeout required')
        req=request.Request('https://api.telegram.org/bot'+self._token+'/sendMessage',data=json.dumps(dict(chat_id=chat_id,text=text,disable_notification=True,protect_content=True)).encode(),headers={'Content-Type':'application/json'},method='POST')
        status=None
        try:
            try:
                response=self.opener.open(req,timeout=timeout_ms/1000)
            except error.HTTPError as exc:
                response=exc
            with response:
                status=response.code; raw=response.read(65537)
            if len(raw)>65536: return DeliveryResult('ambiguous','oversize_response')
            d=json.loads(raw)
            if not isinstance(d,dict) or type(d.get('ok')) is not bool: return DeliveryResult('ambiguous','invalid_response')
            if status==200 and d['ok']:
                m=d.get('result',{}); chat=m.get('chat',{})
                if type(m.get('message_id')) is not int or m['message_id']<=0 or type(chat.get('id')) is not int or chat['id']!=chat_id or m.get('text')!=text: return DeliveryResult('ambiguous','unverified_acceptance')
                return DeliveryResult('sent','telegram_accepted',m['message_id'])
            code=d.get('error_code')
            if d['ok'] is False and code==429 and status in (200,429):
                delay=d.get('parameters',{}).get('retry_after')
                if type(delay) is int and 0<delay<=86400: return DeliveryResult('retry','telegram_rate_limited',retry_after_ms=delay*1000)
                return DeliveryResult('ambiguous','invalid_rate_limit_response')
            if d['ok'] is False and type(code) is int and 400<=code<500 and status in (200,code): return DeliveryResult('failed','telegram_rejected')
            return DeliveryResult('ambiguous','unconfirmed_http_response')
        except (json.JSONDecodeError,UnicodeError,TypeError,AttributeError,ValueError): return DeliveryResult('ambiguous','malformed_response')
        except error.URLError as exc:
            if isinstance(exc.reason,(socket.gaierror,ConnectionRefusedError)): return DeliveryResult('retry','connection_not_established')
            if isinstance(exc.reason,ssl.SSLCertVerificationError): return DeliveryResult('failed','tls_verification_failed')
            return DeliveryResult('ambiguous','network_outcome_unknown')
        except Exception: return DeliveryResult('ambiguous','transport_outcome_unknown')
