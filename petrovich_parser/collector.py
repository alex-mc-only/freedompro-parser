from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Error, Page, Playwright, sync_playwright

from .config import Settings
from .models import ProductRecord, utc_now_iso


class AntiBotBlockedError(RuntimeError):
    """Raised when anti-bot page or non-JSON responses are returned."""


@dataclass
class CollectArtifacts:
    screenshot: Path | None = None
    html_dump: Path | None = None


class PetrovichCollector:
    def __init__(self, settings: Settings, logger: logging.Logger):
        self.settings = settings
        self.logger = logger

    def bootstrap_session(self, manual_wait_seconds: int = 180) -> None:
        self.logger.info("Bootstrap started. Headless mode forced OFF for manual anti-bot solving.")

        with sync_playwright() as playwright:
            browser, context, page = self._launch(playwright, headless=False, with_state=False)
            try:
                page.goto(self.settings.base_url, wait_until="domcontentloaded", timeout=self.settings.nav_timeout_ms)
                self.logger.info(
                    "Browser opened at %s. Complete anti-bot/captcha manually. Waiting %s seconds.",
                    self.settings.base_url,
                    manual_wait_seconds,
                )
                page.wait_for_timeout(manual_wait_seconds * 1000)
                context.storage_state(path=str(self.settings.session_state_file))
                self.logger.info("Session state saved to %s", self.settings.session_state_file)
            finally:
                browser.close()

    def collect_daily(self) -> list[ProductRecord]:
        if not self.settings.session_state_file.exists():
            raise FileNotFoundError(
                f"Session file does not exist: {self.settings.session_state_file}. Run bootstrap mode first."
            )

        with sync_playwright() as playwright:
            browser, context, page = self._launch(playwright, headless=self.settings.headless, with_state=True)
            try:
                page.goto(self.settings.base_url, wait_until="domcontentloaded", timeout=self.settings.nav_timeout_ms)
                page.wait_for_timeout(2500)
                return self._collect_from_api_with_retries(context, page)
            finally:
                browser.close()

    def _launch(
        self,
        playwright: Playwright,
        headless: bool,
        with_state: bool,
    ) -> tuple[Browser, BrowserContext, Page]:
        browser = playwright.chromium.launch(headless=headless)
        kwargs: dict[str, Any] = {
            "viewport": {"width": 1440, "height": 900},
            "locale": "ru-RU",
            "timezone_id": "Europe/Moscow",
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        }
        if with_state:
            kwargs["storage_state"] = str(self.settings.session_state_file)

        context = browser.new_context(**kwargs)
        page = context.new_page()
        return browser, context, page

    def _collect_from_api_with_retries(self, context: BrowserContext, page: Page) -> list[ProductRecord]:
        rows: list[ProductRecord] = []
        offset = 0

        while len(rows) < self.settings.max_products:
            params = {
                "limit": self.settings.page_size,
                "offset": offset,
                "sort": "popularity_desc",
                "path": self.settings.api_path,
                "city_code": self.settings.city_code,
                "client_id": self.settings.client_id,
            }
            payload = self._request_json_with_backoff(context, page, params)
            products = self._extract_products(payload)

            if not products:
                break

            collected_at = utc_now_iso()
            for product in products:
                rows.append(
                    ProductRecord(
                        name=str(product.get("name") or product.get("title") or "").strip(),
                        price=str(self._get_price(product) or "").strip(),
                        article=str(self._get_article(product) or "").strip(),
                        collected_at=collected_at,
                        source_url=self.settings.api_url,
                    )
                )
                if len(rows) >= self.settings.max_products:
                    break

            if len(products) < self.settings.page_size:
                break
            offset += self.settings.page_size

        return [r for r in rows if r.name and r.article]

    def _request_json_with_backoff(
        self,
        context: BrowserContext,
        page: Page,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.request_retries + 1):
            try:
                response = context.request.get(
                    self.settings.api_url,
                    params=params,
                    timeout=self.settings.request_timeout_ms,
                )
                status = response.status
                content_type = (response.header_value("content-type") or "").lower()
                self.logger.info(
                    "API attempt=%s status=%s content_type=%s params=%s",
                    attempt,
                    status,
                    content_type,
                    params,
                )

                if status == 200 and "application/json" in content_type:
                    return response.json()

                snippet = response.text()[:1500]
                self._capture_error_artifacts(page, snippet)

                if status == 403 or "text/html" in content_type:
                    raise AntiBotBlockedError(f"Anti-bot blocked request. status={status}")

                raise RuntimeError(f"Unexpected response: status={status}, content_type={content_type}")
            except (AntiBotBlockedError, Error, json.JSONDecodeError, RuntimeError) as exc:
                last_error = exc
                sleep_s = self.settings.backoff_base_seconds * (2 ** (attempt - 1))
                self.logger.warning(
                    "API request failed on attempt %s/%s (%s). Sleeping %.1fs.",
                    attempt,
                    self.settings.request_retries,
                    exc,
                    sleep_s,
                )
                if attempt < self.settings.request_retries:
                    time.sleep(sleep_s)

        raise RuntimeError(f"Could not get valid JSON from API after retries: {last_error}")

    def _capture_error_artifacts(self, page: Page, response_snippet: str) -> CollectArtifacts:
        slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        screenshot = self.settings.screenshot_dir / f"error_{slug}.png"
        html_dump = self.settings.html_dump_dir / f"error_{slug}.html"

        artifacts = CollectArtifacts()

        try:
            page.screenshot(path=str(screenshot), full_page=True)
            artifacts.screenshot = screenshot
            self.logger.warning("Saved screenshot: %s", screenshot)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Could not save screenshot: %s", exc)

        try:
            html_dump.write_text(
                "<!-- API response snippet -->\n"
                + response_snippet
                + "\n\n<!-- Browser page content -->\n"
                + page.content(),
                encoding="utf-8",
            )
            artifacts.html_dump = html_dump
            self.logger.warning("Saved HTML dump: %s", html_dump)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Could not save HTML dump: %s", exc)

        return artifacts

    @staticmethod
    def _extract_products(data: dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(data, dict):
            if isinstance(data.get("products"), list):
                return data["products"]
            data_node = data.get("data")
            if isinstance(data_node, dict) and isinstance(data_node.get("products"), list):
                return data_node["products"]
        return []

    @staticmethod
    def _get_price(product: dict[str, Any]) -> Any:
        price = product.get("price")
        if isinstance(price, dict):
            return (
                price.get("gold")
                or price.get("actual")
                or price.get("final")
                or price.get("value")
            )
        return price

    @staticmethod
    def _get_article(product: dict[str, Any]) -> Any:
        return (
            product.get("article")
            or product.get("sku")
            or product.get("code")
            or product.get("vendor_code")
        )
