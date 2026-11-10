"""Settings come from environment variables, with defaults for local use."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    db_path: str
    workers: int
    log_level: str


def load_config(env=os.environ):
    return Config(
        host=env.get("JOBQ_HOST", "127.0.0.1"),
        port=int(env.get("JOBQ_PORT", "8080")),
        db_path=env.get("JOBQ_DB", "jobs.db"),
        workers=int(env.get("JOBQ_WORKERS", "4")),
        log_level=env.get("JOBQ_LOG_LEVEL", "INFO"),
    )
