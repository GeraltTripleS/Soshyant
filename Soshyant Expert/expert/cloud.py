"""Opt-in OpenAI-compatible text inference, with server-only credentials."""
import base64
import ctypes
import json
import os
import re
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid


SCHEMA={'type':'object','properties':{'status':{'type':'string','enum':['answered','clarify','insufficient']},
        'answer':{'type':'string'},'citations':{'type':'array','items':{'type':'integer'}}},
        'required':['status','answer','citations'],'additionalProperties':False}


def protect(value, decrypt=False):
    if os.name!='nt':
        # POSIX uses a private (0600) credential file; not encryption at rest.
        return base64.b64decode(value).decode() if decrypt else base64.b64encode(value.encode()).decode()
    class Blob(ctypes.Structure):
        _fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_ubyte))]
    raw=base64.b64decode(value) if decrypt else value.encode()
    buffer=ctypes.create_string_buffer(raw)
    source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));output=Blob()
    library=ctypes.WinDLL('crypt32',use_last_error=True)
    function=library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,
                       ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(Blob)]
    function.restype=ctypes.c_int
    if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(output)):
        raise ValueError('The server account could not access its saved API credential.')
    try:result=ctypes.string_at(output.data,output.size)
    finally:
        free=ctypes.WinDLL('kernel32').LocalFree
        free.argtypes=[ctypes.c_void_p];free.restype=ctypes.c_void_p
        free(ctypes.cast(output.data,ctypes.c_void_p))
    return result.decode() if decrypt else base64.b64encode(result).decode()


class CloudProfiles:
    def __init__(self,config):
        self.config=config;self.path=config.data/'cloud-models.json';self.lock=threading.Lock()

    def rows(self):
        return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else []

    def get(self,identity):
        profile=next((row for row in self.rows() if row['id']==identity),None)
        if not profile:raise ValueError('The saved API model is unavailable. Select a local model or add the connection again.')
        return profile

    @staticmethod
    def public(profile):
        return {key:profile[key] for key in ('id','name','provider','base_url','model','response_mode')}

    def add(self,data):
        provider=data.get('provider','openai')
        if provider not in ('openai','compatible'):raise ValueError('Choose OpenAI or an OpenAI-compatible provider.')
        base='https://api.openai.com/v1' if provider=='openai' else data.get('base_url','')
        if not isinstance(base,str) or len(base)>1000:raise ValueError('Enter a valid HTTPS API base URL.')
        parts=urlsplit(base.strip())
        if parts.scheme!='https' or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('Use an HTTPS API base URL without credentials, query parameters, or fragments.')
        try:parts.port
        except ValueError as exc:raise ValueError('Invalid API endpoint port.') from exc
        model=data.get('model','');name=data.get('name','');key=data.get('api_key','')
        if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}',model):
            raise ValueError('Enter the provider model ID, not a display name or URL.')
        if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise ValueError('Enter a connection name up to 100 characters.')
        if not isinstance(key,str) or not 8<=len(key.strip())<=10000 or any(c.isspace() for c in key.strip()):
            raise ValueError('Enter a valid API key. The key will not be displayed again.')
        mode=data.get('response_mode','json_schema')
        if mode not in ('json_schema','json_object'):raise ValueError('Choose a supported JSON response format.')
        profile={'id':'cloud-'+uuid.uuid4().hex,'name':name.strip(),'provider':provider,
                 'base_url':base.strip().rstrip('/'),'model':model,'response_mode':mode,
                 'secret':protect(key.strip()),'protection':'windows-dpapi' if os.name=='nt' else 'private-file'}
        with self.lock:
            rows=self.rows()
            if len(rows)>=50:raise ValueError('At most 50 API model connections can be saved.')
            rows.append(profile);temporary=self.path.with_suffix('.tmp')
            descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(descriptor,'w',encoding='utf-8') as stream:json.dump(rows,stream,indent=2)
            temporary.replace(self.path)
        return self.public(profile)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class CloudClient:
    def __init__(self,config):
        self.config=config;self.profiles=CloudProfiles(config)
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def generate(self,identity,messages,canceled=lambda:False,probe=False):
        if canceled():raise InterruptedError('Answer canceled.')
        profile=self.profiles.get(identity)
        if profile['protection']!=('windows-dpapi' if os.name=='nt' else 'private-file'):
            raise ValueError('Re-enter the API key on this server account before using this connection.')
        key=protect(profile['secret'],True)
        payload={'model':profile['model'],'messages':messages,'stream':False,
                 'response_format':{'type':profile['response_mode']}}
        if profile['response_mode']=='json_schema':
            payload['response_format']['json_schema']={'name':'grounded_answer','strict':True,'schema':SCHEMA}
        budget=256 if probe else self.config.settings['max_answer_tokens']
        payload['max_completion_tokens' if profile['provider']=='openai' else 'max_tokens']=budget
        if profile['provider']=='openai':payload['store']=False
        request=urllib.request.Request(profile['base_url']+'/chat/completions',data=json.dumps(payload).encode(),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
        try:
            with self.opener.open(request,timeout=120) as response:
                raw=response.read(4*1024*1024+1)
                if len(raw)>4*1024*1024:raise RuntimeError('The provider response exceeded the size limit.')
        except urllib.error.HTTPError as exc:
            # Never reflect provider response text: it may echo credentials or document contents.
            raise RuntimeError(f'API provider returned HTTP {exc.code}. Check the key, model access, endpoint, quota, and JSON format.') from None
        except (urllib.error.URLError,OSError):
            raise RuntimeError('The API provider could not be reached. Check internet access and the HTTPS endpoint.') from None
        if canceled():raise InterruptedError('Answer canceled.')
        try:
            body=json.loads(raw);choice=body['choices'][0]
            if choice.get('finish_reason')!='stop' or choice['message'].get('refusal'):
                raise ValueError('incomplete or refused')
            result=json.loads(choice['message']['content'])
            if not isinstance(result,dict) or result.get('status') not in ('answered','clarify','insufficient') or not isinstance(result.get('answer'),str) or not isinstance(result.get('citations'),list):
                raise ValueError('invalid contract')
            return result
        except (ValueError,KeyError,TypeError,IndexError):
            raise RuntimeError('The API model did not return a complete supported JSON answer. Check model compatibility and output budget.') from None

    def probe(self,identity):
        self.generate(identity,[{'role':'user','content':'Return JSON with status insufficient, answer Connection verified, and citations as an empty array. This is a connection test.'}],probe=True)
