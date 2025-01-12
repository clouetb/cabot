import logging
import random
from datetime import timedelta

from celery import Celery, current_task
from django.utils import timezone
from cabot.celeryconfig import CELERY_DEFAULT_QUEUE

logger = logging.getLogger(__name__)

app = Celery("core")


@app.task(ignore_result=True)
def run_status_check(check_or_id):
    from .models import StatusCheck

    worker_hostname = current_task.request.hostname
    logger.debug(f"Runnning check {check_or_id} on worker {worker_hostname}")
    if not isinstance(check_or_id, StatusCheck):
        check = StatusCheck.objects.get(id=check_or_id)
    else:
        check = check_or_id
    # This will call the subclass method
    check.run(worker_hostname=worker_hostname.replace("celery@", ""))


@app.task(ignore_result=True)
def run_all_checks():
    from .models import StatusCheck
    from datetime import timedelta

    checks = StatusCheck.objects.all()
    seconds = range(60)
    for check in checks:
        if check.last_run:
            next_schedule = check.last_run + timedelta(minutes=check.frequency)
        if (not check.last_run) or timezone.now() > next_schedule:
            target_workers = [
                target_worker.hostname.replace("celery@", "")
                for target_worker in check.target_workers.all()
                if target_worker.is_alive()
            ]
            if not target_workers:
                target_workers.append(CELERY_DEFAULT_QUEUE)
            for target_worker in target_workers:
                delay = random.choice(seconds)
                logger.debug(
                    f"Scheduling check {check} on worker {target_worker} for {delay} seconds from now"
                )
                run_status_check.apply_async(
                    (check.id,), countdown=delay, queue=target_worker
                )


@app.task(ignore_result=True)
def update_services(ignore_result=True):
    # Avoid importerrors and the like from legacy scheduling
    return


@app.task(ignore_result=True)
def update_service(service_or_id):
    from .models import Service

    if not isinstance(service_or_id, Service):
        service = Service.objects.get(id=service_or_id)
    else:
        service = service_or_id
    service.update_status()


@app.task(ignore_result=True)
def update_instance(instance_or_id):
    from .models import Instance

    if not isinstance(instance_or_id, Instance):
        instance = Instance.objects.get(id=instance_or_id)
    else:
        instance = instance_or_id
    instance.update_status()


@app.task(ignore_result=True)
def update_shifts():
    from .models import update_shifts as _update_shifts

    _update_shifts()


@app.task(ignore_result=True)
def clean_db(days_to_retain=7, batch_size=10000):
    """
    Clean up database otherwise it gets overwhelmed with StatusCheckResults.

    To loop over undeleted results, spawn new tasks to make sure db connection closed etc
    """
    from .models import StatusCheckResult, ServiceStatusSnapshot, InstanceStatusSnapshot

    to_discard_results = StatusCheckResult.objects.order_by("time_complete").filter(
        time_complete__lte=timezone.now() - timedelta(days=days_to_retain)
    )
    to_discard_service = ServiceStatusSnapshot.objects.order_by("time").filter(
        time__lte=timezone.now() - timedelta(days=days_to_retain)
    )
    to_discard_instance = InstanceStatusSnapshot.objects.order_by("time").filter(
        time__lte=timezone.now() - timedelta(days=days_to_retain)
    )

    result_ids = to_discard_results[:batch_size].values_list("id", flat=True)
    service_snapshot_ids = to_discard_service[:batch_size].values_list("id", flat=True)
    instance_snapshot_ids = to_discard_instance[:batch_size].values_list(
        "id", flat=True
    )

    result_count = result_ids.count()
    service_snapshot_count = service_snapshot_ids.count()
    instance_snapshot_count = instance_snapshot_ids.count()

    StatusCheckResult.objects.filter(id__in=result_ids).delete()
    ServiceStatusSnapshot.objects.filter(id__in=service_snapshot_ids).delete()
    InstanceStatusSnapshot.objects.filter(id__in=instance_snapshot_ids).delete()

    # If we reached the batch size on either we need to re-queue to continue cleaning up.
    if (
        result_count == batch_size
        or service_snapshot_count == batch_size
        or instance_snapshot_count == batch_size
    ):
        clean_db.apply_async(
            kwargs={"days_to_retain": days_to_retain, "batch_size": batch_size},
            countdown=3,
        )
