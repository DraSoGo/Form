"""Server-only, pool-specific protocols. Never persist upstream error bodies."""
import base64
import os
from dataclasses import dataclass
from urllib.parse import urlsplit
import httpx

class ProviderError(Exception):
    def __init__(self,code,failover=True):
        self.code, self.failover = code, failover
        super().__init__(code)
@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    protocol: str
    key: str
    def __repr__(self): return f'Provider({self.name})'
def providers():
    result = {}
    for name, default in [('claude','messages'),('gpt','responses'),('china','chat')]:
        prefix = f'AI_{name.upper()}'
        base = os.environ.get(prefix+'_BASE_URL','https://api.maxplus-ai.cc/v1').rstrip('/')
        protocol = os.environ.get(prefix+'_PROTOCOL',default)
        parsed = urlsplit(base)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or protocol not in ('messages','responses','chat'):
            raise ProviderError('invalid_provider_configuration',False)
        result[name] = Provider(name,base,protocol,os.environ.get(prefix+'_API_KEY',''))
    return result

def request(provider,path,payload=None):
    if not provider.key: raise ProviderError('key_not_configured')
    try:
        with httpx.Client(timeout=httpx.Timeout(90,connect=8),follow_redirects=False) as client:
            response = client.request('GET' if payload is None else 'POST',provider.base_url+path,
                headers={'Authorization':'Bearer '+provider.key,'anthropic-version':'2023-06-01'},json=payload)
    except httpx.HTTPError: raise ProviderError('network_or_timeout') from None
    status = response.status_code
    if status >= 300:
        if status in (400,404):
            try:
                error=response.json().get('error',{})
                code=error.get('code') or error.get('type') if isinstance(error,dict) else None
            except (ValueError,AttributeError): code=None
            if code in ('model_not_found','invalid_model','unsupported_model'):
                raise ProviderError('incompatible_model')
            if code in ('unsupported_image','vision_not_supported','unsupported_image_input'):
                raise ProviderError('incompatible_vision')
        names = {401:'authentication_failed',402:'insufficient_credit',403:'permission_denied',404:'unavailable_model',408:'timeout',429:'rate_limited'}
        raise ProviderError(names.get(status, 'upstream_unavailable' if status>=500 else 'invalid_request'),status in (401,402,403,404,408,429) or status>=500)
    if len(response.content)>2_000_000: raise ProviderError('response_too_large',False)
    try: return response.json()
    except ValueError: raise ProviderError('invalid_response',False) from None

def complete(provider,model,system,prompt,image=None,max_tokens=2200):
    data_url = 'data:'+image[0]+';base64,'+base64.b64encode(image[1]).decode() if image else None
    if provider.protocol == 'messages':
        content = [{'type':'text','text':prompt}]
        if image: content.append({'type':'image','source':{'type':'base64','media_type':image[0],'data':base64.b64encode(image[1]).decode()}})
        data = request(provider,'/messages',dict(model=model,system=system,messages=[{'role':'user','content':content}],max_tokens=max_tokens,stream=False))
        try: return ''.join(item['text'] for item in data['content'] if item.get('type')=='text')
        except (KeyError,TypeError,AttributeError): raise ProviderError('invalid_response',False) from None
    if provider.protocol == 'responses':
        content = [{'type':'input_text','text':prompt}]
        if image: content.append({'type':'input_image','image_url':data_url})
        data = request(provider,'/responses',dict(model=model,instructions=system,input=[{'role':'user','content':content}],max_output_tokens=max_tokens,store=False,stream=False))
        try: text=''.join(c['text'] for item in data['output'] for c in item.get('content',[]) if c.get('type')=='output_text')
        except (KeyError,TypeError,AttributeError): raise ProviderError('invalid_response',False) from None
        # Gateway intermittently returns status completed with an empty
        # output list while usage shows tokens were produced — a transient
        # upstream fault, so failover to the next candidate instead of
        # returning an empty string that fails schema validation.
        if not text.strip(): raise ProviderError('empty_response')
        return text
    content = [{'type':'text','text':prompt}]
    if image: content.append({'type':'image_url','image_url':{'url':data_url}})
    data = request(provider,'/chat/completions',dict(model=model,messages=[{'role':'system','content':system},{'role':'user','content':content}],max_tokens=max_tokens,stream=False))
    try:
        result=data['choices'][0]['message']['content']
        if not isinstance(result,str): raise TypeError()
        return result
    except (KeyError,IndexError,TypeError): raise ProviderError('invalid_response',False) from None
