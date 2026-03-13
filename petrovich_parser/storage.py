from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from .models import ProductRecord, RunResult


class StorageManager:
    def __init__(self, logger: logging.Logger, run_history_file: Path):
        self.logger = logger
        self.run_history_file = run_history_file

    def write_products_json(self, file_path: Path, rows: list[ProductRecord]) -> None:
        payload = [row.to_dict() for row in rows]
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logger.info("Saved JSON output: %s", file_path)

    def write_products_csv(self, file_path: Path, rows: list[ProductRecord]) -> None:
        with file_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["name", "price", "article", "collected_at", "source_url"],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row.to_dict())
        self.logger.info("Saved CSV output: %s", file_path)

    def safe_write_outputs(
        self,
        rows: list[ProductRecord],
        latest_json: Path,
        latest_csv: Path,
        timestamp_slug: str,
    ) -> tuple[Path, Path]:
        json_timestamped = latest_json.with_name(
            f"{latest_json.stem}_{timestamp_slug}{latest_json.suffix}"
        )
        csv_timestamped = latest_csv.with_name(
            f"{latest_csv.stem}_{timestamp_slug}{latest_csv.suffix}"
        )

        self.write_products_json(json_timestamped, rows)
        self.write_products_csv(csv_timestamped, rows)

        # Update latest snapshots only on non-empty successful run
        self.write_products_json(latest_json, rows)
        self.write_products_csv(latest_csv, rows)

        return json_timestamped, csv_timestamped

    def update_run_history(self, result: RunResult, extras: dict[str, Any] | None = None) -> None:
        data = self._read_history()
        run_data: dict[str, Any] = {
            "ok": result.ok,
            "products_collected": result.products_collected,
            "message": result.message,
            "collected_at": result.collected_at,
        }
        if extras:
            run_data.update(extras)

        data["last_run"] = run_data
        if result.ok:
            data["last_successful_run"] = run_data

        self.run_history_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_history(self) -> dict[str, Any]:
        if not self.run_history_file.exists():
            return {}
        try:
            return json.loads(self.run_history_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self.logger.warning("run_history.json is corrupted; resetting file")
            return {}
