from datetime import datetime
from pydantic import BaseModel
from app.models.finding import Finding


class ScanTask(BaseModel):
    id: str
    repo_url: str
    mr_id: int
    mr_title: str = ""
    status: str = "pending"
    error_message: str = ""
    findings: list[Finding] = []
    created_at: datetime = datetime.now()
    completed_at: datetime | None = None
