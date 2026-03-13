from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_url: str
    api_path: str
    city_code: str
    client_id: str
    output_dir: Path
    logs_dir: Path
    state_dir: Path
    html_dump_dir: Path
    screenshot_dir: Path
    browser_profile_dir: Path
    session_state_file: Path
    latest_json_file: Path
    latest_csv_file: Path
    latest_sqlite_file: Path
    run_history_file: Path
    max_products: int
    page_size: int
    headless: bool
    nav_timeout_ms: int
    request_timeout_ms: int
    request_retries: int
    backoff_base_seconds: float
    min_expected_products: int


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_settings() -> Settings:
    project_root = Path(os.getenv("PETROVICH_PROJECT_ROOT", Path.cwd()))

    data_dir = Path(os.getenv("PETROVICH_DATA_DIR", project_root / "data"))
    output_dir = Path(os.getenv("PETROVICH_OUTPUT_DIR", data_dir / "exports"))
    logs_dir = Path(os.getenv("PETROVICH_LOGS_DIR", data_dir / "logs"))
    state_dir = Path(os.getenv("PETROVICH_STATE_DIR", data_dir / "state"))

    html_dump_dir = state_dir / "html_dumps"
    screenshot_dir = state_dir / "screenshots"
    browser_profile_dir = Path(os.getenv("PETROVICH_BROWSER_PROFILE_DIR", state_dir / "browser_profile"))

    session_state_file = Path(os.getenv("PETROVICH_SESSION_FILE", state_dir / "storage_state.json"))

    latest_json_file = Path(os.getenv("PETROVICH_LATEST_JSON", output_dir / "petrovich_products_latest.json"))
    latest_csv_file = Path(os.getenv("PETROVICH_LATEST_CSV", output_dir / "petrovich_products_latest.csv"))
    latest_sqlite_file = Path(os.getenv("PETROVICH_LATEST_SQLITE", output_dir / "petrovich_products_latest.sqlite"))

    run_history_file = Path(os.getenv("PETROVICH_RUN_HISTORY", state_dir / "run_history.json"))

    return Settings(
        base_url=os.getenv("PETROVICH_BASE_URL", "https://moscow.petrovich.ru"),
        api_url=os.getenv("PETROVICH_API_URL", "https://api.petrovich.ru/catalog/v5/products"),
        api_path=os.getenv("PETROVICH_API_PATH", "/catalog/1547/"),
        city_code=os.getenv("PETROVICH_CITY_CODE", "msk"),
        client_id=os.getenv("PETROVICH_CLIENT_ID", "pet_site"),
        output_dir=output_dir,
        logs_dir=logs_dir,
        state_dir=state_dir,
        html_dump_dir=html_dump_dir,
        screenshot_dir=screenshot_dir,
        browser_profile_dir=browser_profile_dir,
        session_state_file=session_state_file,
        latest_json_file=latest_json_file,
        latest_csv_file=latest_csv_file,
        latest_sqlite_file=latest_sqlite_file,
        run_history_file=run_history_file,
        max_products=int(os.getenv("PETROVICH_MAX_PRODUCTS", "500")),
        page_size=int(os.getenv("PETROVICH_PAGE_SIZE", "50")),
        headless=_env_bool("PETROVICH_HEADLESS", True),
        nav_timeout_ms=int(os.getenv("PETROVICH_NAV_TIMEOUT_MS", "60000")),
        request_timeout_ms=int(os.getenv("PETROVICH_REQUEST_TIMEOUT_MS", "45000")),
        request_retries=int(os.getenv("PETROVICH_REQUEST_RETRIES", "3")),
        backoff_base_seconds=float(os.getenv("PETROVICH_BACKOFF_BASE_SECONDS", "2")),
        min_expected_products=int(os.getenv("PETROVICH_MIN_EXPECTED_PRODUCTS", "1")),
    )


def ensure_directories(settings: Settings) -> None:
    for path in (
        settings.output_dir,
        settings.logs_dir,
        settings.state_dir,
        settings.html_dump_dir,
        settings.screenshot_dir,
        settings.browser_profile_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
