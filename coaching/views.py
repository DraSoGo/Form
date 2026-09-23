import json
import os
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import render,redirect,get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from core.models import FoodEntry
from .models import Job,Analysis,Suggestion,ProviderModel,TaskRoute,TASKS,PushSubscription
from .providers import providers,ProviderError
from .discovery import discover,test_model
from .services import enqueue,daily,decide,enqueue_food
from .push import validate_subscription

@login_required
def home(request):
    return render(request,'coaching/home.html',{'jobs':Job.objects.filter(user=request.user).order_by('-created_at')[:15],'analyses':Analysis.objects.filter(user=request.user).select_related('job').order_by('-local_date','-created_at')[:20],'suggestions':Suggestion.objects.filter(user=request.user).select_related('job').order_by('-created_at')[:30],'vapid_public':os.environ.get('VAPID_PUBLIC_KEY','')})
@login_required
@require_POST
def request_analysis(request,task):
    if task not in ('daily','chat','workout','body'): return JsonResponse({'error':'Invalid task'},status=400)
    if Job.objects.filter(user=request.user,status__in=['pending','running']).count()>=5:
        messages.error(request,'Wait for pending requests before starting another.')
    elif task=='daily': daily(request.user,request.POST.get('reanalyze')=='yes')
    else:
        message=request.POST.get('message','').strip()
        if len(message)>4000: messages.error(request,'Please limit messages to 4,000 characters.')
        elif task=='chat' and not message: messages.error(request,'Enter a question for your coach.')
        else: enqueue(request.user,task,{'message':message})
    return redirect('coaching:home')
@login_required
@require_POST
def retry(request,pk):
    job=get_object_or_404(Job,pk=pk,user=request.user)
    Job.objects.filter(pk=job.pk,status='failed').update(status='pending',attempts=0,error='',lease_until=None)
    return redirect('coaching:home')
@login_required
@require_POST
def decision(request,pk):
    if request.POST.get('decision') not in ('accept','reject'): return JsonResponse({'error':'Invalid decision'},status=400)
    get_object_or_404(Suggestion,pk=pk,user=request.user)
    try: decide(request.user,pk,request.POST['decision']=='accept');messages.success(request,'Decision saved.')
    except ValidationError as exc: messages.error(request,' '.join(exc.messages))
    return redirect('coaching:home')
@login_required
@require_POST
def food(request,pk):
    entry=get_object_or_404(FoodEntry,pk=pk,user=request.user)
    reestimate=request.POST.get('reestimate')=='1'
    try:
        enqueue_food(request.user,entry,reestimate=reestimate)
        messages.success(request,'Food analysis queued. Estimates remain editable in Nutrition.')
    except ValidationError as exc: messages.error(request,' '.join(exc.messages))
    return redirect('coaching:home')
@login_required
def settings_view(request):
    if request.method=='POST':
        try:
            action=request.POST.get('action')
            if action=='discover':
                name=request.POST.get('provider')
                if name not in providers(): raise ValidationError('Unknown provider.')
                count=discover(name);messages.success(request,f'Discovered {count} available models.')
            elif action=='test':
                candidate=get_object_or_404(ProviderModel,pk=request.POST.get('candidate'))
                messages.info(request,test_model(candidate,request.POST.get('vision')=='yes'))
            elif action=='routes':
                task=request.POST.get('task')
                if task not in dict(TASKS): raise ValidationError('Invalid task.')
                ids=[request.POST.get('priority'+str(i)) for i in range(1,4)]
                ids=[pk for pk in ids if pk]
                if len(ids)!=len(set(ids)): raise ValidationError('Each candidate may appear only once.')
                candidates=list(ProviderModel.objects.filter(pk__in=ids,available=True,text_verified=True))
                if len(candidates)!=len(ids) or task=='food' and any(not c.vision_verified for c in candidates): raise ValidationError('Select verified models; food requires verified vision.')
                with transaction.atomic():
                    TaskRoute.objects.filter(task=task).delete()
                    for priority,pk in enumerate(ids): TaskRoute.objects.create(task=task,candidate_id=pk,priority=priority)
                messages.success(request,'Routing priorities saved.')
        except ProviderError as exc: messages.error(request,'Provider test: '+exc.code)
        except (ValidationError,ValueError) as exc: messages.error(request,' '.join(exc.messages) if isinstance(exc,ValidationError) else 'Invalid selection.')
        return redirect('coaching:settings')
    config=[{'name':p.name,'protocol':p.protocol,'configured':bool(p.key)} for p in providers().values()]
    return render(request,'coaching/settings.html',{'providers':config,'models':ProviderModel.objects.all().order_by('provider','model'),'tasks':TASKS,'routes':TaskRoute.objects.select_related('candidate'),'priorities':[1,2,3]})
@login_required
@require_POST
def subscribe(request):
    try:
        data=json.loads(request.body)
        endpoint,keys=validate_subscription(data)
        if data.get('revoke'):
            PushSubscription.objects.filter(user=request.user,endpoint=endpoint).delete()
        else:
            PushSubscription.objects.update_or_create(endpoint=endpoint,defaults={'user':request.user,'keys':keys})
        return JsonResponse({'ok':True})
    except (ValidationError,ValueError,TypeError): return JsonResponse({'error':'Invalid push subscription'},status=400)
