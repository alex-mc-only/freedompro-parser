# Petrovich Products Collector (Resilient mode)

## 1) Техническое заключение

### Почему прошлые попытки не сработали
- **Direct API (`requests`)**: endpoint `https://api.petrovich.ru/catalog/v5/products` стабильно возвращает `403` даже с query params и User-Agent, значит запросы отфильтровываются антиботом на уровне perimeter/WAF.
- **Playwright API через browser context**: даже после установки Chromium и зависимостей в ответе приходил `403` + HTML антибот-страница вместо JSON.
- **HTML парсинг каталога**: в DOM нет товарных карточек, потому что показывается антибот/капча экран.

### Что выбрано
Выбран **наиболее практичный гибридный подход**:
1. **Bootstrap режим (ручной, разово/по необходимости)**:
   - открыть реальный браузер (`headful`),
   - вручную пройти антибот,
   - сохранить `storage_state` (cookies + local/session storage).
2. **Daily collect режим (автоматический, ежедневно)**:
   - использовать сохранённую сессию,
   - пытаться забирать товары из API через Playwright request context,
   - делать retries/backoff,
   - писать логи,
   - при ошибке сохранять диагностические артефакты (screenshot + HTML dump),
   - **не перезаписывать latest-файлы пустыми данными**.

### Почему это лучший вариант сейчас
- Полностью автономный server-side bypass при текущем антиботе **не гарантируется**.
- Этот вариант честно учитывает реальность: нужна валидная пользовательская сессия.
- Решение production-friendly: есть state management, отказоустойчивость, диагностические артефакты, cron/systemd-ready запуск.

---

## 2) Варианты архитектуры (плюсы/минусы)

### A. Прямой `requests` к API
- ✅ Просто и быстро.
- ❌ Уже подтверждённый `403`; ненадёжно.

### B. Headless Playwright без сохранения сессии
- ✅ Ближе к реальному браузеру.
- ❌ Уже подтверждённый `403` + антибот HTML.

### C. Persistent session (выбранный)
- ✅ Реалистичный шанс ежедневной автоматизации после ручного bootstrap.
- ✅ Хорошо автоматизируется через cron/systemd.
- ⚠️ Может требовать повторного bootstrap при протухании сессии.

### D. Запуск на локальной/резидентной сети вместо DC IP
- ✅ Часто лучше проходит антибот.
- ⚠️ Операционно сложнее (инфраструктура/доступность 24/7).

### E. Прокси (residential/mobile)
- ✅ Может снизить блокировки.
- ⚠️ Стоимость, юридические/комплаенс риски, дополнительная поддержка.

### F. Полуавтоматический импорт (CSV/JSON шлюз)
- ✅ Надёжно для downstream-системы.
- ✅ Выбрано: parser отдельно генерирует JSON/CSV, сайт читает готовый файл.

---

## 3) Структура проекта

```text
.
├── main.py
├── petrovich_products_parser.py
├── requirements.txt
├── README.md
├── scripts/
│   └── run_daily.sh
├── data/
│   ├── exports/            # latest + timestamped JSON/CSV
│   ├── logs/               # единый лог-файл
│   └── state/
│       ├── storage_state.json
│       ├── run_history.json
│       ├── html_dumps/
│       └── screenshots/
└── petrovich_parser/
    ├── __init__.py
    ├── config.py
    ├── logger.py
    ├── models.py
    ├── storage.py
    └── collector.py
```

---

## 4) Полный код

Код уже находится в файлах проекта (см. структуру выше), без заглушек и сокращений.

---

## 5) Конфигурация через ENV

Поддерживаемые переменные:
- `PETROVICH_PROJECT_ROOT` (default: cwd)
- `PETROVICH_DATA_DIR` (default: `./data`)
- `PETROVICH_OUTPUT_DIR` (default: `./data/exports`)
- `PETROVICH_LOGS_DIR` (default: `./data/logs`)
- `PETROVICH_STATE_DIR` (default: `./data/state`)
- `PETROVICH_SESSION_FILE` (default: `./data/state/storage_state.json`)
- `PETROVICH_LATEST_JSON` (default: `./data/exports/petrovich_products_latest.json`)
- `PETROVICH_LATEST_CSV` (default: `./data/exports/petrovich_products_latest.csv`)
- `PETROVICH_RUN_HISTORY` (default: `./data/state/run_history.json`)
- `PETROVICH_BASE_URL` (default: `https://moscow.petrovich.ru`)
- `PETROVICH_API_URL` (default: `https://api.petrovich.ru/catalog/v5/products`)
- `PETROVICH_API_PATH` (default: `/catalog/1547/`)
- `PETROVICH_CITY_CODE` (default: `msk`)
- `PETROVICH_CLIENT_ID` (default: `pet_site`)
- `PETROVICH_MAX_PRODUCTS` (default: `500`)
- `PETROVICH_PAGE_SIZE` (default: `50`)
- `PETROVICH_HEADLESS` (default: `true`)
- `PETROVICH_NAV_TIMEOUT_MS` (default: `60000`)
- `PETROVICH_REQUEST_TIMEOUT_MS` (default: `45000`)
- `PETROVICH_REQUEST_RETRIES` (default: `3`)
- `PETROVICH_BACKOFF_BASE_SECONDS` (default: `2`)
- `PETROVICH_MIN_EXPECTED_PRODUCTS` (default: `1`)

---

## 6) Установка и запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

### Bootstrap (ручной)
```bash
python main.py bootstrap --wait-seconds 240 --verbose
```

Что происходит:
- Открывается браузер в headful режиме.
- Вы вручную проходите антибот/капчу.
- По таймауту сохраняется `data/state/storage_state.json`.

### Daily collect
```bash
python main.py collect --verbose
```

Что происходит:
- Загружается сохранённая сессия.
- Идут API-запросы с retry/backoff.
- На успехе пишутся:
  - `data/exports/petrovich_products_latest.json`
  - `data/exports/petrovich_products_latest.csv`
  - timestamped-копии.
- На ошибке:
  - latest-файлы не перезатираются пустыми,
  - пишется `run_history.json`,
  - сохраняются `screenshots` и `html_dumps`.

---

## 7) Ежедневный запуск

### Вариант 1: cron
Открыть cron:
```bash
crontab -e
```
Добавить:
```cron
30 3 * * * /bin/bash /workspace/freedompro-parser/scripts/run_daily.sh >> /workspace/freedompro-parser/data/logs/cron.log 2>&1
```

### Вариант 2: systemd timer
Создать service `/etc/systemd/system/petrovich-collector.service`:
```ini
[Unit]
Description=Petrovich daily collector

[Service]
Type=oneshot
WorkingDirectory=/workspace/freedompro-parser
ExecStart=/usr/bin/python3 /workspace/freedompro-parser/main.py collect
```

Создать timer `/etc/systemd/system/petrovich-collector.timer`:
```ini
[Unit]
Description=Run Petrovich collector daily

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

Включить:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now petrovich-collector.timer
```

---

## 8) Интеграция в happy-boy.ru

Рекомендуемая схема:
1. Этот проект запускается независимо и обновляет `petrovich_products_latest.json`/`csv`.
2. Сайт happy-boy.ru читает latest JSON как источник импорта.
3. Для загрузки использовать upsert по полю `article`.

Формат записи:
```json
{
  "name": "...",
  "price": "...",
  "article": "...",
  "collected_at": "2026-01-01T00:00:00+00:00",
  "source_url": "https://api.petrovich.ru/catalog/v5/products"
}
```

Минимальный ingestion-пайплайн для сайта:
- validate mandatory fields (`name`, `price`, `article`)
- deduplicate by `article`
- upsert into site DB
- сохранить `collected_at` как timestamp выгрузки

---

## 9) Важные ограничения

- Полностью автономный «вечный» обход антибота **не гарантируется**.
- При изменении механизма защиты или протухании cookies потребуется повторный `bootstrap`.
- Для максимальной стабильности лучше запускать collector в среде с «человеческим» IP (не всегда датацентр).
