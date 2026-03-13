from playwright.sync_api import sync_playwright
import pandas as pd
import json

BASE_URL = "https://moscow.petrovich.ru"
API_URL = "https://api.petrovich.ru/catalog/v5/products"
LIMIT_TOTAL = 100
PAGE_SIZE = 20

def extract_products(data):
    # Подстрой под фактический JSON, если нужно
    if isinstance(data, dict):
        if "products" in data and isinstance(data["products"], list):
            return data["products"]
        if "data" in data and isinstance(data["data"], dict) and "products" in data["data"]:
            return data["data"]["products"]
    return []

def get_price(product):
    price = product.get("price")
    if isinstance(price, dict):
        return (
            price.get("gold")
            or price.get("actual")
            or price.get("final")
            or price.get("value")
        )
    return price

def get_article(product):
    return (
        product.get("article")
        or product.get("sku")
        or product.get("code")
        or product.get("vendor_code")
    )

def main():
    rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Открываем сайт, чтобы получить cookies / сессию
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        offset = 0
        while len(rows) < LIMIT_TOTAL:
            params = {
                "limit": PAGE_SIZE,
                "offset": offset,
                "sort": "popularity_desc",
                "path": "/catalog/1547/",
                "city_code": "msk",
                "client_id": "pet_site",
            }

            response = context.request.get(API_URL, params=params, timeout=60000)
            print("STATUS:", response.status)

            if response.status != 200:
                print("Ошибка API:", response.status)
                print(response.text()[:1000])
                break

            data = response.json()
            products = extract_products(data)

            if not products:
                print("Товары не найдены в ответе API")
                print(json.dumps(data, ensure_ascii=False)[:2000])
                break

            for product in products:
                rows.append({
                    "name": product.get("name") or product.get("title"),
                    "price": get_price(product),
                    "article": get_article(product),
                })
                if len(rows) >= LIMIT_TOTAL:
                    break

            if len(products) < PAGE_SIZE:
                break

            offset += PAGE_SIZE

        browser.close()

    df = pd.DataFrame(rows[:LIMIT_TOTAL], columns=["name", "price", "article"])
    df.to_csv("petrovich_products.csv", index=False, encoding="utf-8-sig")
    print(df.head(10))
    print(f"Сохранено {len(df)} товаров в petrovich_products.csv")

if __name__ == "__main__":
    main()