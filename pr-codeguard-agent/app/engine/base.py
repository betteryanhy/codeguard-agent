from abc import ABC, abstractmethod

from app.models.finding import Finding


class AnalysisEngine(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def analyze(self, repo_path: str, diff_files: list[str] | None = None) -> list[Finding]:
        ...
