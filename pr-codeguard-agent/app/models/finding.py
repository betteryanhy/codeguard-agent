from pydantic import BaseModel


class Finding(BaseModel):
    engine: str       # "secrets" | "sast" | "iac" | "best_practice" | "ai_review"
    severity: str     # "blocker" | "critical" | "major" | "minor" | "info"
    file_path: str
    line: int | None = None
    message: str
    code_snippet: str = ""
    recommendation: str = ""
    rule_id: str = ""
    ai_explanation: str = ""
