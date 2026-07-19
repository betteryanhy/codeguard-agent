import uuid
from datetime import datetime


def generate_task_id() -> str:
    return f"task-{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.utcnow()
