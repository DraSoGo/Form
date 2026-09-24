import time
import logging
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.services import retain_images
from coaching.services import schedule,claim_job,run_job
logger=logging.getLogger(__name__)
def maintain():
    from coaching.models import RequestAttempt
    # Diagnostic attempts are logs: keep 90 days, then let them go.
    RequestAttempt.objects.filter(created_at__lt=timezone.now()-timedelta(days=90)).delete()
class Command(BaseCommand):
    help='Poll durable coaching jobs, local-date summary schedule, trend rules and image retention.'
    def add_arguments(self,parser): parser.add_argument('--once',action='store_true')
    def handle(self,*args,**options):
        last_maintenance=0
        while True:
            job=None
            try:
                if time.monotonic()-last_maintenance>=300:
                    schedule();retain_images();maintain();last_maintenance=time.monotonic()
                job=claim_job()
                if job:
                    try: run_job(job)
                    except Exception:
                        # No traceback or upstream text: they can include health context/secrets.
                        from coaching.models import Job
                        Job.objects.filter(pk=job.pk,status='running').update(status='failed',error='internal_processing_error',lease_until=None)
                        logger.error('coaching_job_failed task=%s id=%s',job.task,job.pk)
            except Exception:
                logger.error('coaching_worker_cycle_failed')
            if options['once']: break
            if not job: time.sleep(30)
