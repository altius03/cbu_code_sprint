from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    """All runtime paths resolved from the portable USB home directory."""

    home: Path
    data_dir: Path
    config_dir: Path
    assets_dir: Path
    exports_dir: Path
    backups_dir: Path
    database: Path
    snippets: Path
    lock_file: Path

    @classmethod
    def from_home(cls, home: str | Path) -> "AppPaths":
        resolved = Path(home).expanduser().resolve()
        data_dir = resolved / "data"
        config_dir = resolved / "config"
        return cls(
            home=resolved,
            data_dir=data_dir,
            config_dir=config_dir,
            assets_dir=resolved / "assets",
            exports_dir=resolved / "exports",
            backups_dir=resolved / "backups",
            database=data_dir / "leaderboard.sqlite",
            snippets=config_dir / "snippets.json",
            lock_file=data_dir / "cbu_code_sprint.lock",
        )

    def ensure_directories(self) -> None:
        for directory in [
            self.data_dir,
            self.config_dir,
            self.assets_dir,
            self.exports_dir,
            self.backups_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


def default_home() -> Path:
    """Default to the current working directory for development runs."""

    return Path.cwd().resolve()
