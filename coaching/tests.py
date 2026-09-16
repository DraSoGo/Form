import base64
import json
import tempfile
from datetime import timedelta,datetime,time,timezone as dtz
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import httpx
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase,SimpleTestCase,override_settings
from django.utils import timezone
from pydantic import ValidationError as SchemaError
from core.models import Profile,FoodEntry,BodyMeasurement,SleepEntry,NutritionTarget,Exercise
from core.services import create_target,target_payload
from .models import ProviderModel,TaskRoute,Job,Analysis,Suggestion,RequestAttempt
from .providers import Provider,ProviderError,complete,request
from .router import route
from .schemas import NutritionEstimate, ExerciseMetadata
from .services import enqueue,daily,schedule,claim_job,run_job,decide,on_body_saved,enqueue_food,enqueue_exercise
from .context import build_context
from .triggers import evaluate
from .push import validate_subscription
from .validation import validate_change

SUMMARY={'summary':'Stable recent progress.','highlights':['Protein logged consistently.'],'suggestions':[]}
FOOD={'foods':[{'name':'Rice','amount':'150–200 g'}],'calories':230,'protein':4,'carbs':50,'fat':1,'fiber':2,'sugar':None,'sodium':None,'calories_low':200,'calories_high':280,'confidence':'medium','uncertainty':'Portion is estimated from image.'}
EXERCISE={'aliases':['DB bench press'],'primary_muscles':['Chest'],'secondary_muscles':['Triceps'],'classification':'compound'}
@override_settings(STORAGES={'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}},ALLOWED_HOSTS=['testserver'])
class CoachingTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user(username='coach-owner',password='test-only-passphrase')
        self.profile=Profile.objects.create(user=self.user,summary_time=time(21))
        self.target=create_target(self.user,{'calories':2200,'protein':140,'carbs':260,'fat':70,'fiber':30})
    def candidates(self,task='daily'):
        for index,name in enumerate(['claude','gpt','china']):
            candidate=ProviderModel.objects.create(provider=name,model=name+'-test',text_verified=True)
            TaskRoute.objects.create(task=task,candidate=candidate,priority=index)
    @patch('coaching.router.complete')
    def test_failover_once_and_safe_attempt_metadata(self,mock):
        self.candidates();mock.side_effect=[ProviderError('rate_limited'),ProviderError('insufficient_credit'),json.dumps(SUMMARY)]
        result,provider,model=route('daily',{})
        self.assertEqual(provider,'china');self.assertEqual(mock.call_count,3)
        self.assertEqual(list(RequestAttempt.objects.order_by('sequence').values_list('status',flat=True)),['rate_limited','insufficient_credit','success'])
        self.assertEqual(result,SUMMARY)
    @patch('coaching.router.complete')
    def test_malformed_request_stops_failover(self,mock):
        self.candidates();mock.side_effect=ProviderError('invalid_request',False)
        with self.assertRaises(ProviderError): route('daily',{})
        self.assertEqual(mock.call_count,1)
    @patch('coaching.router.complete')
    def test_schema_failure_stops_without_persisting_analysis(self,mock):
        self.candidates();mock.return_value='{"summary":"bad","execute_sql":"DELETE"}'
        with self.assertRaises(ProviderError) as caught: route('daily',{})
        self.assertEqual(caught.exception.code,'invalid_structured_response');self.assertEqual(mock.call_count,1)
        self.assertEqual(Analysis.objects.count(),0)
    @patch('coaching.router.complete')
    def test_vision_needs_verification(self,mock):
        self.candidates('food')
        with self.assertRaises(ProviderError): route('food',{},image=('image/png',b'test'))
        mock.assert_not_called()
    def test_context_is_bounded_same_source_and_sleep(self):
        for i in range(25): FoodEntry.objects.create(user=self.user,name='food',calories=100,protein=5)
        BodyMeasurement.objects.create(user=self.user,weight=70,source='manual')
        BodyMeasurement.objects.create(user=self.user,weight=72,source='smart_scale')
        SleepEntry.objects.create(user=self.user,hours=7)
        ctx=build_context(self.user,'chat')
        self.assertEqual(set(ctx['body_by_source']),{'manual','smart_scale'})
        self.assertEqual(ctx['windows']['1']['nutrition_totals']['calories'],Decimal(2500))
        self.assertEqual(ctx['windows']['7']['sleep_samples'],1)
        self.assertNotIn('image',str(ctx));self.assertNotIn('password',str(ctx))
    def test_minimum_samples_and_meaningful_trend(self):
        now=timezone.now()
        rows=[{'recorded_at':now-timedelta(days=14-i*2),'weight':70 if i<3 else 74,'body_fat':None} for i in range(6)]
        self.assertEqual(evaluate({'body_by_source':{'manual':rows[:1]}}),[])
        self.assertTrue(evaluate({'body_by_source':{'manual':rows}}))
        split={'manual':rows[:3],'smart_scale':rows[3:]}
        self.assertEqual(evaluate({'body_by_source':split}),[])
    @patch('coaching.services.route')
    def test_default_summary_idempotent_and_reanalysis_versions(self,mock):
        mock.return_value=(SUMMARY,'claude','test')
        first=daily(self.user);again=daily(self.user)
        self.assertEqual(first.pk,again.pk)
        run_job(claim_job());self.assertEqual(Analysis.objects.count(),1)
        self.assertIsNone(claim_job())
        second=daily(self.user,True);self.assertNotEqual(second.pk,first.pk)
        run_job(claim_job());self.assertEqual(list(Analysis.objects.order_by('version').values_list('version',flat=True)),[1,2])
    @patch('coaching.services.on_body_saved')
    def test_scheduler_uses_bangkok_date_and_time(self,mock):
        before=datetime(2026,9,15,13,59,tzinfo=dtz.utc);after=datetime(2026,9,15,14,1,tzinfo=dtz.utc)
        schedule(before);self.assertEqual(Job.objects.count(),0)
        schedule(after);schedule(after);self.assertEqual(Job.objects.count(),1)
        self.assertEqual(Job.objects.get().payload['date'],'2026-09-15')
    def suggestion(self):
        job=enqueue(self.user,'chat')
        before=target_payload(self.target);proposed={**before,'protein':150}
        return Suggestion.objects.create(user=self.user,job=job,kind='nutrition',expected_version=1,before=before,proposed=proposed,reason='Recent protein trend',evidence='Seven days of food history')
    def test_accept_creates_version_reject_does_not_and_stale_rejected(self):
        accepted=self.suggestion();decide(self.user,accepted.pk,True)
        self.assertEqual(NutritionTarget.objects.filter(user=self.user).count(),2)
        self.target.refresh_from_db();self.assertEqual(self.target.protein,140)
        stale=self.suggestion()
        with self.assertRaises(ValidationError): decide(self.user,stale.pk,True)
        decide(self.user,stale.pk,False);self.assertEqual(NutritionTarget.objects.count(),2)
        with self.assertRaises(ValidationError): decide(self.user,accepted.pk,True)
    @patch('coaching.services.route')
    def test_chat_only_stores_suggestion(self,mock):
        suggestion=self.suggestion();change={k:getattr(suggestion,k) for k in ('kind','expected_version','before','proposed','reason','evidence')};suggestion.delete()
        mock.return_value=({**SUMMARY,'suggestions':[change]},'gpt','test')
        job=claim_job();run_job(job)
        self.assertEqual(NutritionTarget.objects.count(),1);self.assertEqual(Suggestion.objects.count(),1)
    @patch('coaching.services.route')
    def test_failure_can_retry_and_does_not_write_output(self,mock):
        mock.side_effect=ProviderError('no_verified_model_configured')
        job=enqueue(self.user,'daily');run_job(claim_job());job.refresh_from_db()
        self.assertEqual(job.status,'failed');self.assertEqual(Analysis.objects.count(),0)
        self.client.force_login(self.user)
        response=self.client.post(f'/coach/retry/{job.pk}/');self.assertEqual(response.status_code,302)
        job.refresh_from_db();self.assertEqual(job.status,'pending')
    def test_authentication_and_post_required(self):
        response=self.client.get('/coach/');self.assertEqual(response.status_code,302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/coach/').status_code,200)
        self.assertEqual(self.client.get('/coach/settings/').status_code,200)
        self.assertEqual(self.client.get('/coach/request/daily/').status_code,405)

    def test_coach_action_controls_use_spaced_groups(self):
        self.client.force_login(self.user)
        response=self.client.get('/coach/')
        self.assertContains(response,'<div class="actions"><form class="action-form"',html=False)
    @patch('coaching.services.route')
    def test_photo_analysis_editable_and_changed_entry_protected(self,mock):
        from PIL import Image
        mock.return_value=(FOOD,'claude','vision-test')
        with tempfile.TemporaryDirectory() as root,override_settings(MEDIA_ROOT=root):
            Image.new('RGB',(16,16),'red').save(Path(root)/'synthetic.jpg')
            entry=FoodEntry.objects.create(user=self.user,name='Photo',image='synthetic.jpg')
            enqueue_food(self.user,entry);run_job(claim_job());entry.refresh_from_db()
            self.assertEqual(entry.state,'ai_estimated');self.assertEqual(entry.calories,230)
            enqueue_food(self.user,entry);entry.calories=250;entry.state='user_corrected';entry.save()
            job=claim_job();run_job(job);job.refresh_from_db();entry.refresh_from_db()
            self.assertEqual(job.error,'food_changed_review_required');self.assertEqual(entry.calories,250)
    def test_extreme_suggestion_rejected(self):
        s=self.suggestion();change={k:getattr(s,k) for k in ('kind','before','proposed')};change['proposed']['calories']=900
        with self.assertRaises(ValidationError): validate_change(self.user,change)
    def test_workout_suggestion_accepts_cardio_duration(self):
        exercise=Exercise.objects.create(user=self.user,name='Walk',activity_type='cardio')
        plan={'name':'Mixed','schedule_type':'rotation','schedule':['Cardio'],
              'exercises':[{'exercise':str(exercise.pk),'day':'Cardio','minutes':30}]}
        validate_change(self.user,{'kind':'workout','before':plan,'proposed':plan})
        invalid={**plan,'exercises':[{**plan['exercises'][0],'minutes':0}]}
        with self.assertRaises(ValidationError):
            validate_change(self.user,{'kind':'workout','before':plan,'proposed':invalid})

    @patch('coaching.services.route')
    def test_exercise_metadata_fills_blanks_only(self, mock):
        mock.return_value=(EXERCISE,'gpt','test')
        exercise=Exercise.objects.create(user=self.user,name='Dumbbell press',secondary_muscles=['Front delts'])
        job=enqueue_exercise(self.user,exercise)
        run_job(claim_job());exercise.refresh_from_db();job.refresh_from_db()
        self.assertEqual(exercise.aliases,['DB bench press'])
        self.assertEqual(exercise.primary_muscles,['Chest'])
        self.assertEqual(exercise.secondary_muscles,['Front delts'])
        self.assertEqual(exercise.classification,'compound')
        self.assertEqual(job.status,'done')

    @patch('coaching.services.route')
    def test_exercise_metadata_rejects_stale_edit(self, mock):
        mock.return_value=(EXERCISE,'gpt','test')
        exercise=Exercise.objects.create(user=self.user,name='Press')
        job=enqueue_exercise(self.user,exercise)
        exercise.primary_muscles=['Shoulders'];exercise.save()
        run_job(claim_job());job.refresh_from_db();exercise.refresh_from_db()
        self.assertEqual(job.error,'exercise_changed_review_required')
        self.assertEqual(exercise.aliases,[])
        self.assertEqual(exercise.primary_muscles,['Shoulders'])

class AdapterTests(SimpleTestCase):
    def test_nutrition_range_validation(self):
        with self.assertRaises(SchemaError): NutritionEstimate.model_validate({**FOOD,'calories_low':500})
    def test_exercise_metadata_schema_is_bounded(self):
        self.assertEqual(ExerciseMetadata.model_validate(EXERCISE).classification,'compound')
        with self.assertRaises(SchemaError): ExerciseMetadata.model_validate({**EXERCISE,'classification':'unknown'})
        with self.assertRaises(SchemaError): ExerciseMetadata.model_validate({**EXERCISE,'primary_muscles':[]})
    @patch('coaching.providers.request')
    def test_each_protocol_image_payload_and_extraction(self,mock):
        samples={'messages':{'content':[{'type':'text','text':'ok'}]},'responses':{'output':[{'content':[{'type':'output_text','text':'ok'}]}]},'chat':{'choices':[{'message':{'content':'ok'}}]}}
        for protocol,data in samples.items():
            mock.return_value=data
            p=Provider('test','https://api.example.test/v1',protocol,'never-print-test-key')
            self.assertEqual(complete(p,'model','system','prompt',image=('image/png',b'image')),'ok')
            self.assertIn(base64.b64encode(b'image').decode(),json.dumps(mock.call_args.args[2]))
            self.assertNotIn('never-print',repr(p))
    @patch('coaching.providers.httpx.Client')
    def test_http_errors_are_safe_and_classified(self,client):
        p=Provider('test','https://api.example.test/v1','chat','test-key')
        for status,failover in [(400,False),(409,False),(413,False),(408,True),(429,True),(402,True),(503,True)]:
            client.return_value.__enter__.return_value.request.return_value=httpx.Response(status,json={'error':'private health info and key'})
            with self.assertRaises(ProviderError) as caught: request(p,'/models')
            self.assertEqual(caught.exception.failover,failover);self.assertNotIn('private',str(caught.exception))
    def test_push_endpoint_validation(self):
        keys={'auth':base64.urlsafe_b64encode(b'a'*16).decode(),'p256dh':base64.urlsafe_b64encode(b'b'*65).decode()}
        validate_subscription({'endpoint':'https://fcm.googleapis.com/fcm/send/test','keys':keys})
        for url in ['http://fcm.googleapis.com/x','https://127.0.0.1/x','https://evil.example/x','https://fcm.googleapis.com:8443/x','https://fcm.googleapis.com.evil.example/x']:
            with self.assertRaises(ValidationError): validate_subscription({'endpoint':url,'keys':keys})

class DiscoveryTests(TestCase):
    @patch('coaching.discovery.request')
    def test_discovery_revokes_missing_models_and_does_not_infer_vision(self,mock):
        from .discovery import discover
        old=ProviderModel.objects.create(provider='gpt',model='old',text_verified=True,vision_verified=True)
        mock.return_value={'data':[{'id':'new'}]}
        self.assertEqual(discover('gpt'),1)
        old.refresh_from_db();self.assertFalse(old.available);self.assertFalse(old.vision_verified)
        self.assertFalse(ProviderModel.objects.get(model='new').vision_verified)
        mock.return_value=[]
        with self.assertRaises(ProviderError): discover('gpt')
    @patch('coaching.discovery.complete')
    def test_capability_requires_correct_image_answer(self,mock):
        from .discovery import test_model
        candidate=ProviderModel.objects.create(provider='gpt',model='test')
        mock.side_effect=['READY','wrong']
        self.assertEqual(test_model(candidate,vision=True),'vision_test_failed')
        self.assertTrue(candidate.text_verified);self.assertFalse(candidate.vision_verified)
        with patch('secrets.choice',return_value='blue'):
            mock.side_effect=['READY','blue']
            self.assertEqual(test_model(candidate,vision=True),'vision_verified')

class ContextRegressionTests(TestCase):
    setUp=CoachingTests.setUp
    suggestion=CoachingTests.suggestion
    def test_older_recurring_food_retrieval_and_missing_day_average(self):
        from core.models import FoodLibrary
        FoodLibrary.objects.create(user=self.user,name='Nutrilite recurring',quantity='34 g',calories=130)
        for i in range(25): FoodLibrary.objects.create(user=self.user,name=f'Other {i}',calories=500)
        ctx=build_context(self.user,'food',query='Nutrilite')
        self.assertEqual(len(ctx['confirmed_foods']),1)
        self.assertEqual(ctx['confirmed_foods'][0]['name'],'Nutrilite recurring')
        FoodEntry.objects.create(user=self.user,name='Logged meal',calories=2100)
        window=build_context(self.user,'chat')['windows']['7']
        self.assertEqual(window['logged_days'],1)
        self.assertEqual(window['nutrition_daily_average']['calories'],2100)
    def test_context_includes_steps_and_completed_training_cardio(self):
        from core.models import StepEntry,Exercise,WorkoutSession,WorkoutCardio
        StepEntry.objects.create(user=self.user,steps=7600)
        exercise=Exercise.objects.create(user=self.user,name='Bike',activity_type='cardio')
        session=WorkoutSession.objects.create(user=self.user,name='Cardio')
        WorkoutCardio.objects.create(session=session,exercise=exercise,minutes=30,completed=True)
        context=build_context(self.user,'body')
        self.assertEqual(context['windows']['1']['steps_total'],7600)
        self.assertEqual(context['workouts'][0]['cardio'][0]['minutes'],30)
    @patch('coaching.services.route')
    def test_invalid_suggestion_rolls_back_whole_analysis(self,mock):
        suggestion=self.suggestion();change={k:getattr(suggestion,k) for k in ('kind','expected_version','before','proposed','reason','evidence')};suggestion.delete()
        change['proposed']['calories']=800
        mock.return_value=({**SUMMARY,'suggestions':[change]},'gpt','test')
        job=claim_job();run_job(job);job.refresh_from_db()
        self.assertEqual(job.status,'failed');self.assertFalse(Analysis.objects.exists());self.assertFalse(Suggestion.objects.exists())
    def test_expired_worker_lease_and_attempt_limit(self):
        job=enqueue(self.user,'chat');job.status='running';job.attempts=3;job.lease_until=timezone.now()-timedelta(seconds=1);job.save()
        self.assertIsNone(claim_job());job.refresh_from_db();self.assertEqual(job.status,'failed')
    def test_push_subscribe_revoke_and_malformed_data(self):
        from .models import PushSubscription
        self.client.force_login(self.user)
        data={'endpoint':'https://fcm.googleapis.com/fcm/send/test','keys':{'auth':base64.urlsafe_b64encode(b'a'*16).decode(),'p256dh':base64.urlsafe_b64encode(b'b'*65).decode()}}
        self.assertEqual(self.client.post('/coach/push/',data=json.dumps(data),content_type='application/json').status_code,200)
        self.assertEqual(PushSubscription.objects.count(),1)
        self.client.post('/coach/push/',data=json.dumps({**data,'revoke':True}),content_type='application/json')
        self.assertEqual(PushSubscription.objects.count(),0)
        for value in [[],None,{'endpoint':123},{**data,'keys':[] }]:
            self.assertEqual(self.client.post('/coach/push/',data=json.dumps(value),content_type='application/json').status_code,400)

class CompatibilityTests(TestCase):
    @patch('coaching.router.complete')
    def test_known_model_failure_disables_candidate_and_fails_over(self,mock):
        for i,name in enumerate(['claude','gpt']):
            candidate=ProviderModel.objects.create(provider=name,model='test',text_verified=True)
            TaskRoute.objects.create(task='daily',candidate=candidate,priority=i)
        mock.side_effect=[ProviderError('incompatible_model'),json.dumps(SUMMARY)]
        self.assertEqual(route('daily',{})[1],'gpt')
        self.assertFalse(ProviderModel.objects.get(provider='claude').available)
        self.assertEqual(mock.call_count,2)
        self.assertEqual(RequestAttempt.objects.count(),2)
    @patch('coaching.providers.httpx.Client')
    def test_known_400_errors_only_are_retryable(self,client):
        p=Provider('test','https://api.example.test/v1','chat','test-key')
        for code,expected,retryable in [('invalid_model','incompatible_model',True),('unsupported_image','incompatible_vision',True),('invalid_request_error','invalid_request',False)]:
            client.return_value.__enter__.return_value.request.return_value=httpx.Response(400,json={'error':{'code':code,'message':'sensitive never logged'}})
            with self.assertRaises(ProviderError) as caught: request(p,'/models')
            self.assertEqual(caught.exception.code,expected);self.assertEqual(caught.exception.failover,retryable)
