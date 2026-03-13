#!/usr/bin/env python3
"""Парсер первых 100 товаров из API Петрович без внешних зависимостей."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Generator, Iterable, List, Optional, Tuple


# =========================
# Настройки
# =========================
URL_CANDIDATES = [
    "https://api.petrovich.ru/catalog/v5/sections/1547/products",
    "https://api.petrovich.ru/catalog/v5/products",
]
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru,en;q=0.9",
    "Connection": "keep-alive",
    "Origin": "https://moscow.petrovich.ru",
    "Referer": "https://moscow.petrovich.ru/catalog/1547/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "x-requested-with": "XmlHttpRequest",
}
COOKIES = {
    "u__geoCityCode": "msk",
    "SIK": "hwAAACLM2HNTasIY_BEIAA",
    "SIV": "1",
    "C_Ge0izsIbpNLRnUSH1ohExbPdgm0": "AAAAAAAACEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA8D8AAGAKUZfqQWlvkBk1r1tl5G_icUt28-k",
    "rerf": "AAAAAGmkWS6y9tjzBpXHAg==",
    "_userGUID": "0:mm7wcrd5:9eoYlJm_MyOVfIVuYv9GESQeWlM2ifaS",
    "FPID": "85b12a68-f96b-4471-ac11-e96773edd875%3D",
    "count_buy": "0",
    "_ym_uid": "176443291346824351",
    "_ym_d": "1772429518",
    "js_FPID": "85b12a68-f96b-4471-ac11-e96773edd875%3D",
    "ser_ym_uid": "176443291346824351",
    "tmr_lvid": "9e71cee824314bdae15d481a03613eb1",
    "tmr_lvidTS": "1764432918003",
    "adrcid": "AHxyJpZu2tfuE6RcdrwehbA",
    "ipp_uid": "1772429521661/bDMthjRJlO9w7Keq/MXoQFJfvbYGgzC3w6YDWGw==",
    "ser_adrcid": "AHxyJpZu2tfuE6RcdrwehbA",
    "adrdel": "1772607350029",
    "acs_3": "%7B%22hash%22%3A%221aa3f9523ee6c2690cb34fc702d4143056487c0d%22%2C%22nst%22%3A1772693750049%2C%22sl%22%3A%7B%22224%22%3A1772607350049%2C%221228%22%3A1772607350049%7D%7D",
    "SNK": "158",
    "u__typeDevice": "desktop",
    "dSesn": "6ed28d1f-0049-2960-b96a-7548d5d2aa01",
    "trueReferrer": "https%3A%2F%2Fmoscow.petrovich.ru%2F",
    "ipp_key": "v1773346901719/e84ee23771/ZeIzZjcTcx2eWVYMgzFJ0rqYNMFNn9TtdJcNKIFI2VR3x1BmNtb2AMPo+N/RBY0I69eHunkflmmjgF6ck3CuOQ==",
    "mindboxDeviceUUID": "c1a14a16-3842-4e7f-b8eb-b61b179f3309",
    "directCrm-session": "%7B%22deviceGuid%22%3A%22c1a14a16-3842-4e7f-b8eb-b61b179f3309%22%7D",
}
BASE_PARAMS = {
    "limit": 20,
    "offset": 0,
    "sort": "popularity_desc",
    "path": "/catalog/1547/",
    "city_code": "msk",
    "client_id": "pet_site",
}
LIMIT = 100
TIMEOUT = 20
OUTPUT_CSV = "petrovich_products.csv"
OUTPUT_JSON = "petrovich_products.json"


def cookie_header(cookies: Dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def walk_json(data: Any) -> Generator[Any, None, None]:
    yield data
    if isinstance(data, dict):
        for value in data.values():
            yield from walk_json(value)
    elif isinstance(data, list):
        for item in data:
            yield from walk_json(item)


def get_by_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def find_products_array(payload: Any) -> List[Dict[str, Any]]:
    by_path = get_by_path(payload, "data.products")
    if isinstance(by_path, list) and all(isinstance(x, dict) for x in by_path):
        return by_path

    if isinstance(payload, list) and all(isinstance(x, dict) for x in payload):
        return payload

    for node in walk_json(payload):
        if isinstance(node, list) and node and all(isinstance(x, dict) for x in node):
            return node
    return []


def find_value_by_candidates(obj: Dict[str, Any], exact_keys: Iterable[str], fuzzy_tokens: Iterable[str]) -> Any:
    exact = {k.lower() for k in exact_keys}
    fuzzy = [t.lower() for t in fuzzy_tokens]

    for k, v in obj.items():
        if str(k).lower() in exact:
            return v
    for k, v in obj.items():
        if any(t in str(k).lower() for t in fuzzy):
            return v
    for v in obj.values():
        if isinstance(v, dict):
            nested = find_value_by_candidates(v, exact, fuzzy)
            if nested is not None:
                return nested
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    nested = find_value_by_candidates(item, exact, fuzzy)
                    if nested is not None:
                        return nested
    return None


def normalize_price(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw.replace(" ", "").replace(",", "."))
        except ValueError:
            return None
    if isinstance(raw, dict):
        for key in ("gold", "price", "value", "amount", "current", "final", "sale"):
            if key in raw:
                val = normalize_price(raw[key])
                if val is not None:
                    return val
    if isinstance(raw, list):
        for item in raw:
            val = normalize_price(item)
            if val is not None:
                return val
    return None


def extract_product_fields(item: Dict[str, Any]) -> Dict[str, Any]:
    raw_name = get_by_path(item, "title")
    raw_price = get_by_path(item, "price.gold")
    raw_article = get_by_path(item, "code")

    if raw_name is None:
        raw_name = find_value_by_candidates(item, ("title", "name", "product_name"), ("title", "name"))
    if raw_price is None:
        raw_price = find_value_by_candidates(item, ("price", "cost", "amount"), ("price", "cost"))
    if raw_article is None:
        raw_article = find_value_by_candidates(item, ("code", "article", "sku", "vendor_code"), ("code", "article", "sku"))

    return {
        "name": str(raw_name).strip() if raw_name is not None else None,
        "price": normalize_price(raw_price),
        "article": str(raw_article).strip() if raw_article is not None else None,
    }


def fetch_json(url: str, params: Dict[str, Any]) -> Any:
    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}"
    req = urllib.request.Request(full_url, method="GET")
    for k, v in HEADERS.items():
        req.add_header(k, v)
    req.add_header("Cookie", cookie_header(COOKIES))

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP ошибка {exc.code} для URL {full_url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Сетевая ошибка для URL {full_url}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Неожиданный JSON для URL {full_url}") from exc


def fetch_payload_with_fallback(params: Dict[str, Any]) -> Tuple[Any, str]:
    errors: List[str] = []
    for url in URL_CANDIDATES:
        try:
            return fetch_json(url, params), url
        except RuntimeError as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("; ".join(errors))


def has_more(payload: Any, received_count: int, page_size: int, next_offset: int) -> bool:
    if isinstance(payload, dict):
        total = payload.get("total") or payload.get("count") or payload.get("total_count")
        if isinstance(total, int):
            return next_offset < total
    return received_count >= page_size


def fetch_first_products(limit: int = LIMIT) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    page_size = int(BASE_PARAMS.get("limit", 20))
    offset = int(BASE_PARAMS.get("offset", 0))

    while len(rows) < limit:
        params = dict(BASE_PARAMS)
        params["offset"] = offset

        payload, _ = fetch_payload_with_fallback(params)
        products = find_products_array(payload)
        if not products:
            break

        for product in products:
            rows.append(extract_product_fields(product))
            if len(rows) >= limit:
                break

        if len(rows) >= limit:
            break

        next_offset = offset + page_size
        if not has_more(payload, len(products), page_size, next_offset):
            break
        offset = next_offset

    return rows[:limit]


def save_to_csv(rows: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "price", "article"])
        writer.writeheader()
        writer.writerows(rows)


def save_to_json(rows: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def run_self_test() -> None:
    """Проверка в офлайн-режиме на тестовом payload без сети."""
    payload = {
        "data": {
            "products": [
                {"title": "Товар 1", "code": "A1", "price": {"gold": 101.5}},
                {"title": "Товар 2", "code": "A2", "price": {"gold": "202,40"}},
            ]
        },
        "total": 2,
    }
    products = find_products_array(payload)
    rows = [extract_product_fields(p) for p in products]
    assert len(rows) == 2
    assert rows[0]["name"] == "Товар 1"
    assert rows[0]["article"] == "A1"
    assert abs(rows[1]["price"] - 202.40) < 1e-9

    save_to_csv(rows, "selftest_products.csv")
    save_to_json(rows, "selftest_products.json")
    print("SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true", help="Запустить офлайн самопроверку без сети")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return

    try:
        rows = fetch_first_products(LIMIT)
    except Exception as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        sys.exit(1)

    save_to_csv(rows, OUTPUT_CSV)
    save_to_json(rows, OUTPUT_JSON)
    print(json.dumps(rows[:20], ensure_ascii=False, indent=2))
    print(f"\nСохранено в файлы: {OUTPUT_CSV}, {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
