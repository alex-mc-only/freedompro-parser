from __future__ import annotations

import argparse
from datetime import datetime, timezone

from petrovich_parser.collector import PetrovichCollector
from petrovich_parser.config import ensure_directories, load_settings
from petrovich_parser.logger import configure_logging
from petrovich_parser.models import RunResult, utc_now_iso
from petrovich_parser.storage import StorageManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resilient Petrovich products collector")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose console logs")

    subparsers = parser.add_subparsers(dest="mode", required=True)

    bootstrap_parser = subparsers.add_parser(
        "bootstrap", help="Local manual anti-bot bootstrap: open browser and save session state"
    )
    bootstrap_parser.add_argument(
        "--wait-seconds",
        type=int,
        default=180,
        help="How many seconds to keep browser open for manual captcha solve",
    )

    bootstrap_remote_parser = subparsers.add_parser(
        "bootstrap-remote",
        help="Server-side manual bootstrap with persistent profile (run via xvfb/vnc)",
    )
    bootstrap_remote_parser.add_argument("--wait-seconds", type=int, default=300)
    bootstrap_remote_parser.add_argument("--remote-debugging-port", type=int, default=9222)

    attach_parser = subparsers.add_parser(
        "attach-to-browser",
        help="Attach to an already running remote Chromium (CDP) and save session state",
    )
    attach_parser.add_argument("--cdp-url", required=True, help="Example: http://127.0.0.1:9222")
    attach_parser.add_argument("--wait-seconds", type=int, default=180)

    subparsers.add_parser("collect", help="Run daily collection using saved session state")

    return parser


def run() -> int:
    parser = build_parser()
    args = parser.parse_args()

    settings = load_settings()
    ensure_directories(settings)

    logger = configure_logging(settings.logs_dir, verbose=args.verbose)
    storage = StorageManager(logger=logger, run_history_file=settings.run_history_file)
    collector = PetrovichCollector(settings=settings, logger=logger)

    if args.mode == "bootstrap":
        collector.bootstrap_session(manual_wait_seconds=args.wait_seconds)
        storage.update_run_history(
            RunResult(ok=True, products_collected=0, message="bootstrap completed", collected_at=utc_now_iso())
        )
        return 0

    if args.mode == "bootstrap-remote":
        collector.bootstrap_remote(
            manual_wait_seconds=args.wait_seconds,
            remote_debugging_port=args.remote_debugging_port,
        )
        storage.update_run_history(
            RunResult(ok=True, products_collected=0, message="bootstrap-remote completed", collected_at=utc_now_iso())
        )
        return 0

    if args.mode == "attach-to-browser":
        collector.attach_to_existing_browser(cdp_url=args.cdp_url, manual_wait_seconds=args.wait_seconds)
        storage.update_run_history(
            RunResult(ok=True, products_collected=0, message="attach-to-browser completed", collected_at=utc_now_iso())
        )
        return 0

    try:
        rows = collector.collect_daily()
        if len(rows) < settings.min_expected_products:
            message = (
                "Collected too few products. "
                f"Got={len(rows)}, expected_at_least={settings.min_expected_products}. "
                "Latest successful files were kept unchanged."
            )
            logger.error(message)
            storage.update_run_history(
                RunResult(ok=False, products_collected=len(rows), message=message, collected_at=utc_now_iso())
            )
            return 2

        ts_slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        json_file, csv_file, sqlite_file = storage.safe_write_outputs(
            rows=rows,
            latest_json=settings.latest_json_file,
            latest_csv=settings.latest_csv_file,
            latest_sqlite=settings.latest_sqlite_file,
            timestamp_slug=ts_slug,
        )

        msg = f"Collected {len(rows)} products"
        logger.info(msg)
        storage.update_run_history(
            RunResult(ok=True, products_collected=len(rows), message=msg, collected_at=utc_now_iso()),
            extras={
                "latest_json": str(settings.latest_json_file),
                "latest_csv": str(settings.latest_csv_file),
                "latest_sqlite": str(settings.latest_sqlite_file),
                "timestamped_json": str(json_file),
                "timestamped_csv": str(csv_file),
                "timestamped_sqlite": str(sqlite_file),
            },
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        message = f"Collection failed: {exc}"
        logger.exception(message)
        storage.update_run_history(
            RunResult(ok=False, products_collected=0, message=message, collected_at=utc_now_iso())
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
