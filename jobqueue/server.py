"""HTTP API built on http.server.

POST /jobs        {"kind": "add", "payload": {"numbers": [1, 2]}}  -> 201 {"id": ...}
GET  /jobs/<id>   -> 200 job, or 404
GET  /health      -> 200
"""

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jobqueue.config import load_config
from jobqueue.store import JobStore
from jobqueue.tasks import TASKS
from jobqueue.workers import WorkerPool

log = logging.getLogger("jobqueue")


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": True})
            if self.path.startswith("/jobs/"):
                job = store.get(self.path[len("/jobs/"):])
                if job is None:
                    return self._send(404, {"error": "job not found"})
                return self._send(200, job)
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/jobs":
                return self._send(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"error": "body must be JSON"})
            kind = body.get("kind") if isinstance(body, dict) else None
            if kind not in TASKS:
                return self._send(400, {"error": f"kind must be one of {sorted(TASKS)}"})
            payload = body.get("payload", {})
            if not isinstance(payload, dict):
                return self._send(400, {"error": "payload must be an object"})
            job_id = store.add(kind, payload)
            log.info("queued job %s (%s)", job_id, kind)
            self._send(201, {"id": job_id, "status": "queued"})

        def log_message(self, fmt, *args):  # route http.server's own lines through logging
            log.debug("%s %s", self.address_string(), fmt % args)

    return Handler


def main():
    config = load_config()
    logging.basicConfig(level=config.log_level, format="%(asctime)s %(threadName)s %(levelname)s %(message)s")
    store = JobStore(config.db_path)
    pool = WorkerPool(store, config.workers)
    pool.start()
    server = ThreadingHTTPServer((config.host, config.port), make_handler(store))
    log.info("listening on http://%s:%d", config.host, config.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        pool.stop()


if __name__ == "__main__":
    main()
