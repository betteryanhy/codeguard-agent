"""Scan strategy configuration - per-repo scanning policy management.

Allows users to configure different scanning intensity and behavior for
each repository or globally as a default.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ── Strategy levels ──────────────────────────────────────────────────

SCAN_LEVEL_LIGHT = "light"      # Quick scan: only IAC + secrets, no deep analysis
SCAN_LEVEL_STANDARD = "standard"  # Default: all engines enabled
SCAN_LEVEL_DEEP = "deep"         # Full scan: all engines + AI enrichment

VALID_LEVELS = (SCAN_LEVEL_LIGHT, SCAN_LEVEL_STANDARD, SCAN_LEVEL_DEEP)


# ── Data Model ───────────────────────────────────────────────────────

@dataclass
class ScanStrategy:
    """Per-repository scanning strategy configuration.

    Fields:
        repo_url: Unique repository URL. Use "__default__" for the global default.
        scan_level: light / standard / deep
        engines_enabled: Dict of engine name -> bool
        branch_trigger_patterns: List of branch glob patterns that trigger scans.
                                 Empty = all branches.
        risk_threshold: Minimum severity to trigger alert (info, low, medium, high, critical)
        alert_on_findings: Whether to send alerts for findings in this repo
        auto_comment: Whether to post scan results as MR comment
        post_comment_only_risks: Only post risks to MR comments (not info-level)
        ai_enabled: Whether to run AI enrichment
        tf_change_detection: Whether to detect Terraform resource changes
        created_at / updated_at: Timestamps
    """
    repo_url: str = "__default__"
    scan_level: str = SCAN_LEVEL_STANDARD
    engines_enabled: dict = field(default_factory=lambda: {
        "secrets": True,
        "sast": True,
        "iac": True,
        "best_practice": True,
        "trivy": True,
    })
    branch_trigger_patterns: list = field(default_factory=lambda: [
        "feature/*", "fix/*", "hotfix/*", "test/*",
    ])
    risk_threshold: str = "medium"
    alert_on_findings: bool = True
    auto_comment: bool = True
    post_comment_only_risks: bool = True
    ai_enabled: bool = False
    tf_change_detection: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        # Handle both datetime and string types for DB compatibility
        def _fmt(val):
            if isinstance(val, datetime):
                return val.isoformat()
            if isinstance(val, str):
                return val
            return None
        d["created_at"] = _fmt(self.created_at)
        d["updated_at"] = _fmt(self.updated_at)
        return d

    def is_default(self) -> bool:
        return self.repo_url == "__default__"


# ── Strategy Service ─────────────────────────────────────────────────

DEFAULT_STRATEGY = ScanStrategy()


class ScanStrategyManager:
    """Manages scan strategies with SQLite persistence."""

    def __init__(self, db_path: str = "./data/knowledge.db"):
        self._db_path = db_path
        self._cache: dict[str, ScanStrategy] = {}
        self._init_table()

    # ── DB ───────────────────────────────────────────────────────────

    def _connect(self):
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_table(self):
        conn = self._connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_strategies (
                    repo_url TEXT PRIMARY KEY,
                    config TEXT NOT NULL,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)
            conn.commit()
            self._load_cache(conn)
        finally:
            conn.close()

    def _load_cache(self, conn=None):
        """Load all strategies into cache."""
        close = conn is None
        if close:
            conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM scan_strategies").fetchall()
            self._cache = {}
            for row in rows:
                try:
                    config = json.loads(row["config"])
                    config["repo_url"] = row["repo_url"]
                    config["created_at"] = self._parse_dt(config.get("created_at"))
                    config["updated_at"] = self._parse_dt(config.get("updated_at"))
                    self._cache[row["repo_url"]] = ScanStrategy(**config)
                except Exception as e:
                    logger.warning("Failed to load strategy for %s: %s", row["repo_url"], e)
        finally:
            if close:
                conn.close()

    @staticmethod
    def _parse_dt(val):
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, TypeError):
                pass
        return val

    # ── CRUD ─────────────────────────────────────────────────────────

    def get_default(self) -> ScanStrategy:
        """Get the global default strategy."""
        return self._cache.get("__default__", DEFAULT_STRATEGY)

    def get_strategy(self, repo_url: str) -> ScanStrategy:
        """Get effective strategy for a repo.

        Priority: per-repo overrides > global defaults.
        Returns a merged strategy where each field comes from the per-repo
        config if it was explicitly overridden, otherwise from the global default.
        This ensures that changes to the global default propagate to repos
        that haven't explicitly overridden a given field.
        """
        default = self.get_default()
        if repo_url == "__default__" or repo_url not in self._cache:
            return default

        per_repo = self._cache[repo_url]

        # Detect which fields were explicitly overridden by comparing
        # the per-repo values against the original factory defaults
        original_defaults = ScanStrategy()
        overrides = {}
        for field in ScanStrategy.__dataclass_fields__:
            if field in ("repo_url", "created_at", "updated_at"):
                continue
            per_repo_val = getattr(per_repo, field)
            orig_val = getattr(original_defaults, field)
            if per_repo_val != orig_val:
                overrides[field] = per_repo_val

        # Start with current global defaults, overlay explicit overrides
        merged_dict = default.to_dict()
        merged_dict["repo_url"] = repo_url
        merged_dict.update(overrides)
        merged_dict["created_at"] = per_repo.created_at or default.created_at
        merged_dict["updated_at"] = per_repo.updated_at or default.updated_at

        return ScanStrategy(**merged_dict)

    def list_strategies(self) -> list[ScanStrategy]:
        """List all per-repo strategies with their effective (merged) config."""
        return [
            self.get_strategy(repo_url)
            for repo_url in self._cache
            if repo_url != "__default__"
        ]

    def save_strategy(self, strategy: ScanStrategy) -> bool:
        """Save or update a strategy.

        Per-repo strategies are stored as diffs (only fields that differ from
        the current global default). This ensures that changes to the global
        default propagate to repos that haven't explicitly overridden a field.
        """
        now = datetime.utcnow()
        if strategy.repo_url in self._cache:
            strategy.updated_at = now
        else:
            strategy.created_at = now
            strategy.updated_at = now

        conn = self._connect()
        try:
            if strategy.repo_url != "__default__":
                # Per-repo: store only diff vs current global default
                default = self.get_default()
                diff = {}
                for field in ScanStrategy.__dataclass_fields__:
                    if field in ("repo_url", "created_at", "updated_at"):
                        continue
                    strat_val = getattr(strategy, field)
                    default_val = getattr(default, field)
                    if strat_val != default_val:
                        diff[field] = strat_val
                config_dict = diff
            else:
                config_dict = asdict(strategy)
                config_dict.pop("repo_url", None)

            # Convert datetimes to strings for JSON
            if strategy.created_at:
                config_dict["created_at"] = strategy.created_at.isoformat()
                config_dict["updated_at"] = strategy.updated_at.isoformat() if strategy.updated_at else strategy.created_at.isoformat()

            conn.execute(
                """INSERT OR REPLACE INTO scan_strategies (repo_url, config, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (strategy.repo_url, json.dumps(config_dict, ensure_ascii=False),
                 strategy.created_at, strategy.updated_at),
            )
            conn.commit()

            # Update cache: for per-repo, store factory defaults + overrides
            if strategy.repo_url != "__default__":
                full_config = {}
                for field in ScanStrategy.__dataclass_fields__:
                    if field in ("repo_url", "created_at", "updated_at"):
                        continue
                    full_config[field] = diff.get(field, getattr(ScanStrategy(), field))
                full_config["repo_url"] = strategy.repo_url
                full_config["created_at"] = strategy.created_at
                full_config["updated_at"] = strategy.updated_at
                self._cache[strategy.repo_url] = ScanStrategy(**full_config)
            else:
                self._cache[strategy.repo_url] = strategy
            return True
        except Exception as e:
            logger.error("Failed to save strategy for %s: %s", strategy.repo_url, e)
            return False
        finally:
            conn.close()

    def delete_strategy(self, repo_url: str) -> bool:
        """Delete a strategy. Cannot delete the default."""
        if repo_url == "__default__":
            return False
        conn = self._connect()
        try:
            conn.execute("DELETE FROM scan_strategies WHERE repo_url = ?", (repo_url,))
            conn.commit()
            self._cache.pop(repo_url, None)
            return True
        except Exception as e:
            logger.error("Failed to delete strategy for %s: %s", repo_url, e)
            return False
        finally:
            conn.close()

    # ── Query helpers for scanners ───────────────────────────────────

    def should_scan_branch(self, repo_url: str, branch: str) -> bool:
        """Check if this branch should be scanned based on strategy patterns."""
        strategy = self.get_strategy(repo_url)
        if not strategy.branch_trigger_patterns:
            return True  # Empty = scan all branches
        import fnmatch
        for pattern in strategy.branch_trigger_patterns:
            if fnmatch.fnmatch(branch, pattern):
                return True
        return False

    def get_enabled_engines(self, repo_url: str) -> list[str]:
        """Get list of enabled engine names for this repo."""
        strategy = self.get_strategy(repo_url)
        return [
            name for name, enabled in strategy.engines_enabled.items()
            if enabled
        ]

    def should_alert(self, repo_url: str, severity: str) -> bool:
        """Check if a finding with this severity should trigger an alert."""
        strategy = self.get_strategy(repo_url)
        if not strategy.alert_on_findings:
            return False
        severity_order = ["info", "low", "medium", "high", "critical"]
        threshold = strategy.risk_threshold
        try:
            return severity_order.index(severity) >= severity_order.index(threshold)
        except (ValueError, IndexError):
            return False

    def should_comment(self, repo_url: str) -> bool:
        """Check if MR comments should be posted for this repo."""
        return self.get_strategy(repo_url).auto_comment

    def should_enable_ai(self, repo_url: str) -> bool:
        """Check if AI enrichment is enabled for this repo."""
        return self.get_strategy(repo_url).ai_enabled

    def should_detect_tf_changes(self, repo_url: str) -> bool:
        """Check if Terraform change detection is enabled."""
        return self.get_strategy(repo_url).tf_change_detection
