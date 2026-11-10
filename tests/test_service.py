import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from jobqueue.config import load_config
from jobqueue.server import make_handler
from jobqueue.store import JobStore
from jobqueue.workers import WorkerPool


def wait_for(store, job_id, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        job = store.get(job_id)
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "jobs.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_running_job_is_requeued_after_restart(self):
        store = JobStore(self.path)
        job_id = store.add("count_words", {"text": "a b"})
        store.claim_next()
        self.assertEqual(store.get(job_id)["status"], "running")
        store2 = JobStore(self.path)  # a "restart"
        self.assertEqual(store2.get(job_id)["status"], "queued")

    def test_no_job_is_claimed_twice(self):
        store = JobStore(self.path)
        ids = {store.add("count_words", {"text": "x " * i}) for i in range(40)}
        claimed, lock = [], threading.Lock()

        def claim():
            while (job := store.claim_next()) is not None:
                with lock:
                    claimed.append(job["id"])

        threads = [threading.Thread(target=claim) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(claimed), sorted(ids))  # each exactly once


class WorkerTests(unittest.TestCase):
    def test_jobs_run_at_the_same_time(self):
        with tempfile.TemporaryDirectory() as d:
            store = JobStore(os.path.join(d, "jobs.db"))
            pool = WorkerPool(store, size=4, poll_seconds=0.01)
            ids = [store.add("sleep", {"seconds": 1}) for _ in range(4)]
            start = time.time()
            pool.start()
            for job_id in ids:
                self.assertEqual(wait_for(store, job_id)["status"], "done")
            pool.stop()
            self.assertLess(time.time() - start, 2.5)  # 4 x 1s one by one would be 4s

    def test_failing_job_is_marked_failed(self):
        with tempfile.TemporaryDirectory() as d:
            store = JobStore(os.path.join(d, "jobs.db"))
            pool = WorkerPool(store, size=1, poll_seconds=0.01)
            job_id = store.add("count_words", {"wrong": 1})  # skipped validation, as an old row might
            pool.start()
            job = wait_for(store, job_id)
            pool.stop()
            self.assertEqual(job["status"], "failed")
            self.assertIn("text", job["error"])


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = JobStore(os.path.join(cls.tmp.name, "jobs.db"))
        cls.pool = WorkerPool(cls.store, size=2, poll_seconds=0.01)
        cls.pool.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.store))
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.pool.stop()
        cls.tmp.cleanup()

    def request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def test_submit_and_read(self):
        status, body = self.request("POST", "/jobs", {"type": "count_words", "text": "one two three"})
        self.assertEqual(status, 201)
        job = wait_for(self.store, body["id"])
        status, job = self.request("GET", f"/jobs/{body['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["result"], {"words": 3})

    def test_bad_jobs_are_400(self):
        for body in [{"type": "format_disk"}, {"type": "sleep", "seconds": 60}, {"type": "sleep", "seconds": "3"},
                     {"type": "count_words"}, ["not", "an", "object"]]:
            status, _ = self.request("POST", "/jobs", body)
            self.assertEqual(status, 400, body)

    def test_bad_json_is_400(self):
        req = urllib.request.Request(self.base + "/jobs", data=b"{oops", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_missing_job_is_404(self):
        status, _ = self.request("GET", "/jobs/nope")
        self.assertEqual(status, 404)


class ConfigTests(unittest.TestCase):
    def test_env_overrides(self):
        config = load_config({"JOBQ_PORT": "9000", "JOBQ_WORKERS": "8"})
        self.assertEqual((config.port, config.workers), (9000, 8))


if __name__ == "__main__":
    unittest.main()
