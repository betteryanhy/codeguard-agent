from pydantic import BaseModel


class RepoConfig(BaseModel):
    repo_url: str
    enabled_engines: list[str] = ["secrets", "sast", "iac", "best_practice"]
    webhook_secret: str = ""
    active: bool = True
