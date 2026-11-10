"""The two kinds of job. validate() checks a payload when the job is submitted, so a bad job is
refused with 400 instead of failing later."""

import time


def count_words(payload):
    return {"words": len(payload["text"].split())}


def sleep(payload):
    time.sleep(payload["seconds"])
    return {"slept": payload["seconds"]}


TASKS = {"count_words": count_words, "sleep": sleep}


def validate(kind, payload):
    """Returns an error message, or None if the job is fine."""
    if kind not in TASKS:
        return f"type must be one of {sorted(TASKS)}"
    if not isinstance(payload, dict):
        return "payload must be an object"
    if kind == "count_words" and not isinstance(payload.get("text"), str):
        return "count_words needs a text string"
    if kind == "sleep":
        seconds = payload.get("seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 1 <= seconds <= 10:
            return "sleep needs seconds from 1 to 10"
    return None
