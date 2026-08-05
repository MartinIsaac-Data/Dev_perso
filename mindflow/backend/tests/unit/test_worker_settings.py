"""The worker as arq itself reads it.

Every other test in this suite calls the job functions directly, which is the
right way to test what they do and says nothing about whether the process
starts. It does not: `arq.worker.get_kwargs` reads `WorkerSettings.__dict__`
instead of doing attribute lookup, so a descriptor left in the class body is
handed to arq verbatim. That cost us a worker that raised
`'staticmethod' object has no attribute 'host'` before running a single job —
invisible to 892 passing tests, and fatal to every capture in the queue.

So these tests go through arq's own loader rather than around it.
"""

from __future__ import annotations

from arq.connections import RedisSettings
from arq.worker import get_kwargs

from app.infra.queue.arq_queue import QUEUE_REALTIME
from app.workers.pipeline.runner import PROCESS_CAPTURE
from app.workers.settings import WorkerSettings


def test_arq_reads_a_usable_redis_configuration() -> None:
    kwargs = get_kwargs(WorkerSettings)

    settings = kwargs["redis_settings"]
    assert isinstance(settings, RedisSettings)
    # `create_pool` reads these two directly; the failure mode this guards is an
    # object that looks configured and has neither.
    assert settings.host
    assert settings.port


def test_the_worker_registers_the_capture_pipeline_under_the_name_the_api_uses() -> None:
    # The API enqueues by name and arq names a job from `__qualname__`, so the
    # two agree only if this says so. When they disagree the job is accepted,
    # never run, and the capture sits at `uploaded` for ever.
    kwargs = get_kwargs(WorkerSettings)
    assert [fn.name for fn in kwargs["functions"]] == [PROCESS_CAPTURE]


def test_the_worker_listens_on_the_queue_the_api_writes_to() -> None:
    # One layer below the name: right function, wrong queue, same silence.
    kwargs = get_kwargs(WorkerSettings)
    assert kwargs["queue_name"] == QUEUE_REALTIME


def test_every_scheduled_job_survives_the_same_loader() -> None:
    kwargs = get_kwargs(WorkerSettings)
    names = {job.name for job in kwargs["cron_jobs"]}

    # The two jobs whose absence is silent and dated: partitions that stop
    # covering next month, and integrations that stop syncing.
    assert "cron:partition_job" in names
    assert "cron:sync_job" in names
    assert len(names) == len(kwargs["cron_jobs"])
