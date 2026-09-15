import base64
import json
import os
from urllib.parse import urlsplit
from django.core.exceptions import ValidationError
from .models import PushSubscription

# Fixed browser push service hosts prevent server-side requests to arbitrary endpoints.
HOSTS=('fcm.googleapis.com','updates.push.services.mozilla.com','web.push.apple.com')
def validate_subscription(data):
    if not isinstance(data,dict): raise ValidationError('Invalid subscription.')
    endpoint=data.get('endpoint','')
    if not isinstance(endpoint,str): raise ValidationError('Invalid endpoint.')
    parts=urlsplit(endpoint)
    if parts.scheme!='https' or parts.hostname not in HOSTS or parts.port not in (None,443) or parts.username or parts.password or parts.fragment or len(endpoint)>2000:
        raise ValidationError('Unsupported browser push endpoint.')
    keys=data.get('keys',{})
    if not isinstance(keys,dict): raise ValidationError('Invalid keys.')
    for key,size in [('auth',16),('p256dh',65)]:
        try:
            value=keys[key]
            if not isinstance(value,str): raise ValueError()
            decoded=base64.b64decode(value+'='*(-len(value)%4),altchars=b'-_',validate=True)
            if len(decoded)!=size: raise ValueError()
        except (KeyError,ValueError,TypeError): raise ValidationError('Invalid push subscription keys.') from None
    return endpoint,{k:keys[k] for k in ('auth','p256dh')}

def notify(user,event):
    private=os.environ.get('VAPID_PRIVATE_KEY')
    if not private: return
    from pywebpush import webpush,WebPushException
    message={'title':'Fitness Coach','body':'Your daily summary is ready.' if event=='daily' else 'A suggested change is ready to review.','url':'/coach/'}
    for subscription in PushSubscription.objects.filter(user=user):
        try:
            webpush(subscription_info={'endpoint':subscription.endpoint,'keys':subscription.keys},data=json.dumps(message),vapid_private_key=private,vapid_claims={'sub':os.environ.get('VAPID_SUBJECT','mailto:admin@example.com')},timeout=10)
        except WebPushException as exc:
            if exc.response is not None and exc.response.status_code in (404,410): subscription.delete()
