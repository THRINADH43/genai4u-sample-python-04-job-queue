"""A fixed pool of worker threads that take queued jobs from the store and run them."""

import logging
import threading

from jobqueue.tasks import TASKS

log = logging.getLogger(__name__)


class WorkerPool:
    def __init__(self, store, size, poll_seconds=0.2):
        self.store = store
        self.size = size
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._threads = []

    def start(self):
        for i in range(self.size):
            t = threading.Thread(target=self._run, name=f"worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)
        log.info("started %d workers", self.size)

    def stop(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=5)

    def _run(self):
        while not self._stop.is_set():
            job = self.store.claim_next()
            if job is None:
                self._stop.wait(self.poll_seconds)
                continue
            self.run_job(job)

    def run_job(self, job):
        log.info("running job %s (%s)", job["id"], job["kind"])
        try:
            result = TASKS[job["kind"]](job["payload"])
        except Exception as err:  # a bad job must not kill the worker
            log.warning("job %s failed: %s", job["id"], err)
            self.store.finish(job["id"], error=str(err))
        else:
            self.store.finish(job["id"], result=result)
            log.info("job %s done", job["id"])
