from io import BytesIO
from PIL import Image
from django.utils import timezone
from .models import ProviderModel
from .providers import providers,request,complete,ProviderError

def discover(name):
    provider=providers()[name]
    data=request(provider,'/models')
    if not isinstance(data,dict) or 'data' not in data: raise ProviderError('invalid_model_list',False)
    rows=data['data']
    if not isinstance(rows,list): raise ProviderError('invalid_model_list',False)
    models={r['id'] for r in rows if isinstance(r,dict) and isinstance(r.get('id'),str) and len(r['id'])<=200}
    ProviderModel.objects.filter(provider=name).exclude(model__in=models).update(available=False,text_verified=False,vision_verified=False)
    for model in models:
        ProviderModel.objects.update_or_create(provider=name,model=model,defaults={'available':True})
    return len(models)

def test_model(candidate,vision=False):
    provider=providers()[candidate.provider]
    candidate.text_verified=False
    try:
        text=complete(provider,candidate.model,'Follow the instruction exactly.','Reply with the single word READY.',max_tokens=64)
        if text.strip().strip('.').upper()!='READY': raise ProviderError('text_test_failed',False)
        candidate.text_verified=True
        if vision:
            import secrets
            color=secrets.choice(['red','green','blue'])
            buffer=BytesIO(); Image.new('RGB',(64,64),color).save(buffer,format='PNG')
            result=complete(provider,candidate.model,'Identify the image.','What is the dominant color? Reply with one English color word only.',image=('image/png',buffer.getvalue()),max_tokens=64)
            candidate.vision_verified=result.strip().strip('.').lower()==color
            if not candidate.vision_verified: raise ProviderError('vision_test_failed',False)
        candidate.status='vision_verified' if candidate.vision_verified else 'text_verified'
    except ProviderError as exc:
        if vision: candidate.vision_verified=False
        else: candidate.text_verified=False
        candidate.status=exc.code
    candidate.tested_at=timezone.now()
    candidate.save()
    return candidate.status
