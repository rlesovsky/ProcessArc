import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent


def _is_frozen() -> bool:
    """True when running inside a PyInstaller bundle (the .exe build).

    PyInstaller sets `sys.frozen = True` and `sys._MEIPASS` to the temp
    extraction directory. In that mode, BACKEND_ROOT / PROJECT_ROOT point
    into a temp dir that gets wiped on each launch — useless for user
    data.
    """
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _user_data_dir() -> Path:
    """OS-appropriate per-user data directory for the desktop build.

    - Windows: %APPDATA%\\ProcessArc        (e.g. C:\\Users\\<u>\\AppData\\Roaming\\ProcessArc)
    - macOS:   ~/Library/Application Support/ProcessArc
    - Linux:   $XDG_CONFIG_HOME/processarc  (or ~/.config/processarc)

    We hand-roll this rather than depending on `platformdirs` so the
    config module stays import-light. The three platforms above are all
    we ship for.
    """
    if sys.platform == "win32":
        import os
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "ProcessArc"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ProcessArc"
    # Linux / other Unix
    import os
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "processarc"


# Source of truth for where the app reads/writes:
# - Dev mode (running from a checkout):  backend/.env, <repo>/projects, <repo>/templates
# - Frozen mode (the .exe):              <user-data-dir>/.env, <user-data-dir>/projects, ...
#
# Both modes look the same from the app's perspective — only the paths
# change. Tests run in dev mode.
_DATA_ROOT = _user_data_dir() if _is_frozen() else BACKEND_ROOT
_PROJECTS_DEFAULT = (_user_data_dir() if _is_frozen() else PROJECT_ROOT) / "projects"
_TEMPLATES_DEFAULT = (_user_data_dir() if _is_frozen() else PROJECT_ROOT) / "templates"
ENV_FILE = _DATA_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    claude_model: str = Field(default="claude-sonnet-4-6", alias="CLAUDE_MODEL")

    projects_dir: Path = Field(default=_PROJECTS_DEFAULT, alias="PROJECTS_DIR")
    templates_dir: Path = Field(default=_TEMPLATES_DEFAULT, alias="TEMPLATES_DIR")

    # The .env file (location varies by mode: see ENV_FILE above) is the
    # source of truth for this tool — a stale OS env var (e.g. an empty
    # ANTHROPIC_API_KEY exported by another app) must not shadow the value
    # the engineer just saved through the UI.
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    @property
    def has_api_key(self) -> bool:
        return bool(self.anthropic_api_key) and not self.anthropic_api_key.startswith("sk-ant-replace")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.projects_dir.mkdir(parents=True, exist_ok=True)
    s.templates_dir.mkdir(parents=True, exist_ok=True)
    return s


def reload_settings() -> Settings:
    """Drop the cached Settings so the next get_settings() re-reads .env."""
    get_settings.cache_clear()
    return get_settings()


def upsert_env_var(key: str, value: str | None) -> None:
    """Set KEY=value in backend/.env. If value is None, remove the line.

    Preserves other lines and blank-line layout. Creates the file if missing.
    """
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []

    prefix = f"{key}="
    found = False
    new_lines: list[str] = []
    for line in lines:
        if line.lstrip().startswith(prefix):
            if value is not None and not found:
                new_lines.append(f"{key}={value}")
                found = True
            # if value is None, drop the line; if already replaced, drop duplicates
            continue
        new_lines.append(line)

    if value is not None and not found:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
