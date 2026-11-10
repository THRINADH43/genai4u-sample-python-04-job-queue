# Job queue web service

A small HTTP service, written with only the Python standard library, that accepts jobs,
runs them in the background with a pool of worker threads, and reports their status. Jobs
are stored in SQLite, so they survive a restart.

## Run

```
python -m jobqueue.server
```

Then, in another terminal:

```
curl -X POST localhost:8080/jobs -d '{"kind": "add", "payload": {"numbers": [1, 2, 3]}}'
# {"id": "3f2c...", "status": "queued"}
curl localhost:8080/jobs/3f2c...
# {"id": "3f2c...", "status": "done", "result": {"sum": 6}, ...}
```

Job kinds: `add` (`numbers`), `sleep` (`seconds`, at most 30) and `word_count` (`text`).

## Endpoints

| Method | Path        | Answer |
|--------|-------------|--------|
| POST   | `/jobs`     | 201 with the job id; 400 for bad JSON, an unknown kind or a bad payload |
| GET    | `/jobs/<id>`| 200 with the job; 404 if there is no such job |
| GET    | `/health`   | 200 |

## Configuration

| Variable         | Default     |
|------------------|-------------|
| `JOBQ_HOST`      | `127.0.0.1` |
| `JOBQ_PORT`      | `8080`      |
| `JOBQ_DB`        | `jobs.db`   |
| `JOBQ_WORKERS`   | `4`         |
| `JOBQ_LOG_LEVEL` | `INFO`      |

## How it works

- `server.py` handles HTTP with `ThreadingHTTPServer` and only adds jobs to the store.
- `workers.py` starts `JOBQ_WORKERS` threads. Each one claims the oldest queued job and runs it.
- `store.py` keeps jobs in SQLite. Every thread opens its own connection (SQLite connections
  must not be shared between threads), and claiming a job happens under a lock, so two
  workers never run the same job. A test starts 6 threads claiming 40 jobs and checks each
  job is claimed exactly once.
- When the server starts, jobs left as `running` by a crash are put back in the queue.
- A job that raises an error is marked `failed` with the message; the worker keeps going.

## Tests

```
python -m unittest discover -s tests -t . -v
```

The same command runs in GitHub Actions on every push (`.github/workflows/tests.yml`).
