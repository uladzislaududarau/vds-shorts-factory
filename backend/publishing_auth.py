"""OAuth for the publishing channel, separate from the downloader's Chrome session."""
import base64
import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
from urllib.parse import urlencode
import httpx
from .config import ROOT

REDIRECT='http://127.0.0.1:8765/api/publishing/oauth/callback'
SCOPE='https://www.googleapis.com/auth/youtube.force-ssl'
LOCK=threading.RLock()
FLOWS={}

def private_path(name):
    folder=ROOT/'.secrets'/'publishing'
    folder.mkdir(mode=0o700,parents=True,exist_ok=True);folder.chmod(0o700)
    return folder/name

def read(name):
    path=private_path(name)
    return json.loads(path.read_text()) if path.exists() else None

def write(name,value):
    path=private_path(name)
    descriptor,temporary=tempfile.mkstemp(dir=path.parent,prefix='.writing-')
    try:
        with os.fdopen(descriptor,'w') as stream: json.dump(value,stream)
        os.replace(temporary,path);path.chmod(0o600)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

def save_client(value):
    is_web='web' in value
    value=value.get('web') or value.get('installed') or value
    if not isinstance(value,dict):raise ValueError('Нужен JSON OAuth-клиента Google')
    cid=value.get('client_id','');secret=value.get('client_secret','')
    if not isinstance(cid,str) or not cid.endswith('.apps.googleusercontent.com') or len(cid)>300:
        raise ValueError('Нужен OAuth Client ID Google, оканчивающийся на .apps.googleusercontent.com')
    if not isinstance(secret,str) or not 5<=len(secret)<=512 or any(c.isspace() for c in secret):
        raise ValueError('Некорректный OAuth Client Secret')
    redirects=value.get('redirect_uris')
    if is_web and REDIRECT not in (redirects or []):
        raise ValueError('Добавьте redirect URI '+REDIRECT+' в OAuth-клиент Google')
    with LOCK:
        previous=read('client.json')
        write('client.json',{'client_id':cid,'client_secret':secret})
        if previous and previous['client_id']!=cid:
            private_path('token.json').unlink(missing_ok=True)
        FLOWS.clear()
    return status()

def status():
    client=read('client.json');token=read('token.json')
    return {'configured':bool(client),'connected':bool(token and token.get('channel')),
            'channel':token.get('channel') if token else None,'redirect_uri':REDIRECT,
            'note':'Подключение для публикаций отдельно от скачивания. Отключение не отменяет расписание, уже сохранённое в YouTube.'}

def connect():
    client=read('client.json')
    if not client: raise ValueError('Сначала добавьте OAuth Client JSON или Client ID/Secret в настройках публикации')
    state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    with LOCK:
        for key in list(FLOWS):
            if FLOWS[key]['expires']<time.time(): FLOWS.pop(key,None)
        FLOWS[state]={'expires':time.time()+600,'verifier':verifier,'client_id':client['client_id']}
    return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':client['client_id'],'redirect_uri':REDIRECT,
        'response_type':'code','scope':SCOPE,'access_type':'offline','prompt':'consent select_account','state':state,
        'code_challenge':challenge,'code_challenge_method':'S256'})}

def token_request(data):
    try:
        with httpx.Client(timeout=30,follow_redirects=False) as client:
            result=client.post('https://oauth2.googleapis.com/token',data=data)
    except httpx.HTTPError:
        raise ValueError('Google не ответил при авторизации. Повторите подключение.') from None
    if result.status_code!=200:
        raise ValueError('Google отклонил авторизацию. Проверьте OAuth-клиент, redirect URI и Test users; при истёкшем доступе войдите заново.')
    value=result.json()
    if not value.get('access_token'): raise ValueError('Google не вернул токен доступа')
    return value

def callback(state,code,error=None):
    with LOCK:
        flow=FLOWS.pop(state,None)
    if not flow or flow['expires']<time.time(): raise ValueError('Ссылка входа истекла или уже использована. Нажмите «Подключить канал» заново.')
    if error: raise ValueError('Вход отменён или Google не выдал разрешение на публикацию')
    client=read('client.json')
    if not client or client['client_id']!=flow['client_id']: raise ValueError('OAuth-клиент изменился. Повторите вход.')
    result=token_request({'client_id':client['client_id'],'client_secret':client['client_secret'],'code':code,
        'grant_type':'authorization_code','redirect_uri':REDIRECT,'code_verifier':flow['verifier']})
    if not result.get('refresh_token'): raise ValueError('Google не выдал offline-доступ. Повторите подключение с подтверждением разрешений.')
    if SCOPE not in result.get('scope','').split(): raise ValueError('Не выдано разрешение YouTube для загрузки и управления расписанием')
    channel=channel_for(result['access_token'])
    result.update(channel=channel,expires_at=time.time()+result.get('expires_in',3600)-60)
    with LOCK: write('token.json',result)
    return channel

def channel_for(token):
    try:
        with httpx.Client(timeout=30,follow_redirects=False) as client:
            response=client.get('https://www.googleapis.com/youtube/v3/channels',params={'part':'snippet','mine':'true'},headers={'Authorization':'Bearer '+token})
    except httpx.HTTPError: raise ValueError('Не удалось получить подключённый канал YouTube') from None
    if response.status_code!=200: raise ValueError('Не удалось получить канал. Включите YouTube Data API v3 и проверьте доступ аккаунта.')
    items=response.json().get('items',[])
    if len(items)!=1: raise ValueError('Выберите один конкретный YouTube-канал при входе, затем повторите подключение')
    item=items[0]
    return {'id':item['id'],'title':item['snippet']['title']}

def access_token(expected_channel=None):
    with LOCK:
        token=read('token.json');client=read('client.json')
        if not token or not client: raise ValueError('Подключите канал в Настройки → Публикации')
        if expected_channel and token.get('channel',{}).get('id')!=expected_channel:
            raise ValueError('Подключён другой канал. Эта партия закреплена за исходным каналом; автоматического переноса нет.')
        if token.get('expires_at',0)<time.time():
            result=token_request({'client_id':client['client_id'],'client_secret':client['client_secret'],
                'refresh_token':token['refresh_token'],'grant_type':'refresh_token'})
            token.update(result);token['expires_at']=time.time()+result.get('expires_in',3600)-60;write('token.json',token)
        return token['access_token']

def verify_channel():
    token=read('token.json')
    if not token: raise ValueError('Сначала подключите канал')
    channel=channel_for(access_token(token['channel']['id']))
    if channel['id']!=token['channel']['id']: raise ValueError('Google вернул другой канал. Повторите подключение.')
    token=read('token.json');token['channel']=channel;write('token.json',token)
    return status()

def disconnect():
    with LOCK:
        private_path('token.json').unlink(missing_ok=True);FLOWS.clear()
    return status()

# Never retain OAuth authorization codes in the local access log.
class OAuthLogFilter(__import__('logging').Filter):
    def filter(self,record):
        if isinstance(record.args,tuple) and len(record.args)>=3 and isinstance(record.args[2],str) and '/api/publishing/oauth/callback' in record.args[2]:
            args=list(record.args);args[2]=args[2].split('?')[0];record.args=tuple(args)
        return True
__import__('logging').getLogger('uvicorn.access').addFilter(OAuthLogFilter())
