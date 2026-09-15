import uuid
from django.conf import settings
from django.db import models

TASKS = [('food','Food Vision'),('workout','Workout Analysis'),('body','Body / Progress Analysis'),('daily','Daily Summary'),('chat','Coach Chat')]
class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: abstract = True
class ProviderModel(Record):
    provider = models.CharField(max_length=12)
    model = models.CharField(max_length=200)
    available = models.BooleanField(default=True)
    text_verified = models.BooleanField(default=False)
    vision_verified = models.BooleanField(default=False)
    tested_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=60, default='Not tested')
    class Meta: constraints = [models.UniqueConstraint(fields=['provider','model'],name='coach_unique_model')]
class TaskRoute(models.Model):
    task = models.CharField(max_length=12, choices=TASKS)
    candidate = models.ForeignKey(ProviderModel,on_delete=models.CASCADE)
    priority = models.PositiveSmallIntegerField()
    class Meta:
        ordering = ['priority','pk']
        constraints = [models.UniqueConstraint(fields=['task','candidate'],name='coach_unique_route')]
class Job(Record):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    task = models.CharField(max_length=12,choices=TASKS)
    dedupe = models.CharField(max_length=180,unique=True)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=12,default='pending',db_index=True)
    lease_until = models.DateTimeField(null=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.CharField(max_length=160,blank=True)
    result = models.JSONField(default=dict)
    provider = models.CharField(max_length=12,blank=True)
    model = models.CharField(max_length=200,blank=True)
class Analysis(Record):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    job = models.OneToOneField(Job,on_delete=models.CASCADE)
    task = models.CharField(max_length=12)
    local_date = models.DateField()
    version = models.PositiveIntegerField(default=1)
    content = models.JSONField()
    class Meta: constraints = [models.UniqueConstraint(fields=['user','task','local_date','version'],name='coach_analysis_version')]
class Suggestion(Record):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    job = models.ForeignKey(Job,on_delete=models.CASCADE)
    kind = models.CharField(max_length=12)
    expected_version = models.PositiveIntegerField()
    before = models.JSONField()
    proposed = models.JSONField()
    reason = models.TextField()
    evidence = models.TextField()
    decision = models.CharField(max_length=12,default='pending')
    decided_at = models.DateTimeField(null=True)
class PushSubscription(Record):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    endpoint = models.URLField(max_length=2000,unique=True)
    keys = models.JSONField()
class RequestAttempt(Record):
    job = models.ForeignKey(Job,on_delete=models.CASCADE,null=True,related_name='request_attempts')
    task = models.CharField(max_length=12)
    provider = models.CharField(max_length=12)
    model = models.CharField(max_length=200)
    sequence = models.PositiveSmallIntegerField()
    latency_ms = models.PositiveIntegerField()
    status = models.CharField(max_length=60)
