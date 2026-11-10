"""The kinds of job the service can run. Each takes the payload dict and returns a result."""

import time


def add_numbers(payload):
    return {"sum": sum(payload["numbers"])}


def sleep(payload):
    seconds = float(payload.get("seconds", 1))
    if not 0 <= seconds <= 30:
        raise ValueError("seconds must be between 0 and 30")
    time.sleep(seconds)
    return {"slept": seconds}


def word_count(payload):
    return {"words": len(payload["text"].split())}


TASKS = {"add": add_numbers, "sleep": sleep, "word_count": word_count}
