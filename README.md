# Petrovich Products Collector (remote-only workflow)

## 1) Выбранный remote-only подход

**Выбранная стратегия: `xvfb + fluxbox + x11vnc (+опционально noVNC) + persistent browser profile + session_state`**.

Почему именно она:
- прямой API (`requests`) и browser-context API уже подтверждённо дают `403`/антибот;
- headful bootstrap реально нужен для прохождения антибота;
- на сервере нет X server, значит нужен виртуальный дисплей;
- `xvfb + vnc` позволяет пройти антибот **полностью на сервере**, без локального запуска браузера;
- после прохождения сохраняются:
  - `storage_state.json` (cookie/storage для fast reuse),
  - `data/state/browser_profile/` (persistent профиль браузера);
- дальше `collect` работает как daily job в headless, пока сессия валидна.

---

## 2) Architecture decision

### Почему прошлые попытки не сработали
1. `requests` к `https://api.petrovich.ru/catalog/v5/products` и `.../sections/1547/products` стабильно возвращает `403` (WAF/anti-bot).
2. Playwright `context.request` с серверного IP также может получать anti-bot HTML вместо JSON.
3. HTML-каталог на сервере часто показывает антибот/капчу, а не карточки.

### Почему предыдущий коммит не закрывал задачу
- Bootstrap был только headful локально (`main.py bootstrap`) и падал без X server.
- Без bootstrap отсутствовал `storage_state.json`, поэтому `collect` не запускался.
- Значит не было полноценного удалённого цикла.

### Что автоматизировано сейчас
- Полный server-side bootstrap (`bootstrap-remote`) через виртуальный дисплей.
- Сохранение session state и persistent profile на сервере.
- Автоматический daily collect.
- Выход в JSON/CSV/SQLite.
- Защита latest от перезаписи пустым результатом.
- retries/backoff, run_history, diagnostics (screenshot/html dumps).

### Что остаётся ручным шагом
- Антибот/капча прохождение во время bootstrap (через VNC/noVNC).

### Ограничения
- Полностью автономный bypass антибота не гарантируется.
- При протухании сессии нужен повторный remote bootstrap.

---

## 3) Полная структура проекта

```text
.
├── main.py
├── petrovich_products_parser.py
├── requirements.txt
├── README.md
├── scripts/
│   ├── run_daily.sh
│   └── bootstrap_remote_vnc.sh
├── data/
│   ├── exports/
│   ├── logs/
│   └── state/
│       ├── browser_profile/
│       ├── storage_state.json
│       ├── run_history.json
│       ├── html_dumps/
│       └── screenshots/
└── petrovich_parser/
    ├── __init__.py
    ├── collector.py
    ├── config.py
    ├── logger.py
    ├── models.py
    └── storage.py
```

---

## 4) Полный код

См. полный исходный код в репозитории (все файлы перечислены выше; без заглушек).

---

## 5) Установка

```bash
cd /workspace/freedompro-parser
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
sudo apt-get update
sudo apt-get install -y xvfb x11vnc fluxbox
# noVNC optional:
pip install novnc
```

---

## 6) CLI режимы

```bash
python main.py --help
python main.py bootstrap --help
python main.py bootstrap-remote --help
python main.py attach-to-browser --help
python main.py collect --help
```

### `bootstrap`
Локальный headful bootstrap (legacy сценарий).

### `bootstrap-remote`
Server-side bootstrap с persistent profile, рассчитан на Xvfb/VNC окружение.

### `attach-to-browser`
Подключение к уже запущенному Chromium по CDP (`--cdp-url`) и сохранение state.

### `collect`
Ежедневный сбор с использованием `storage_state.json`.

---

## 7) Remote bootstrap: пошагово (без локального браузера)

### Вариант A (рекомендуется): готовый скрипт

```bash
cd /workspace/freedompro-parser
source .venv/bin/activate
WAIT_SECONDS=360 ./scripts/bootstrap_remote_vnc.sh
```

После запуска:
- подключитесь к серверу по VNC на порт `5901`,
- либо по noVNC на `http://SERVER_IP:6080` (если установлен `novnc_proxy`),
- в открытом Chromium вручную пройдите антибот,
- дождитесь окончания таймера.

Состояние сохранится в:
- `data/state/storage_state.json`
- `data/state/browser_profile/`

### Вариант B: attach к существующему браузеру

Если Chromium уже поднят как отдельный сервис с `--remote-debugging-port=9222`:

```bash
python main.py attach-to-browser --cdp-url http://127.0.0.1:9222 --wait-seconds 240 --verbose
```

---

## 8) Daily collect и расписание

### Разовый запуск

```bash
python main.py collect --verbose
```

### Cron

```cron
30 3 * * * /bin/bash /workspace/freedompro-parser/scripts/run_daily.sh >> /workspace/freedompro-parser/data/logs/cron.log 2>&1
```

### Systemd timer (production)

`/etc/systemd/system/petrovich-collector.service`
```ini
[Unit]
Description=Petrovich daily collector

[Service]
Type=oneshot
WorkingDirectory=/workspace/freedompro-parser
ExecStart=/bin/bash /workspace/freedompro-parser/scripts/run_daily.sh
```

`/etc/systemd/system/petrovich-collector.timer`
```ini
[Unit]
Description=Run Petrovich collector daily

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now petrovich-collector.timer
```

---

## 9) Output форматы для happy-boy.ru

Пишутся файлы:
- `data/exports/petrovich_products_latest.json`
- `data/exports/petrovich_products_latest.csv`
- `data/exports/petrovich_products_latest.sqlite`
- timestamped copies каждого формата.

Структура полей:
- `name`
- `price`
- `article`
- `collected_at`
- `source_url`

Рекомендуемый импорт в happy-boy.ru:
- читать `*_latest.json` (или SQLite),
- upsert по `article`,
- валидировать `name/price/article` как обязательные.

---

## 10) Надёжность и диагностика

Реализовано:
- retries/backoff для API попыток;
- distinction: мало/0 товаров = неуспех, latest не перезаписывается;
- `run_history.json` с `last_run` и `last_successful_run`;
- на ошибках: screenshot + html dump;
- детальный лог: `data/logs/petrovich_collector.log`.

---

## 11) ENV переменные

- `PETROVICH_PROJECT_ROOT`
- `PETROVICH_DATA_DIR`
- `PETROVICH_OUTPUT_DIR`
- `PETROVICH_LOGS_DIR`
- `PETROVICH_STATE_DIR`
- `PETROVICH_BROWSER_PROFILE_DIR`
- `PETROVICH_SESSION_FILE`
- `PETROVICH_LATEST_JSON`
- `PETROVICH_LATEST_CSV`
- `PETROVICH_LATEST_SQLITE`
- `PETROVICH_RUN_HISTORY`
- `PETROVICH_BASE_URL`
- `PETROVICH_API_URL`
- `PETROVICH_API_PATH`
- `PETROVICH_CITY_CODE`
- `PETROVICH_CLIENT_ID`
- `PETROVICH_MAX_PRODUCTS`
- `PETROVICH_PAGE_SIZE`
- `PETROVICH_HEADLESS`
- `PETROVICH_NAV_TIMEOUT_MS`
- `PETROVICH_REQUEST_TIMEOUT_MS`
- `PETROVICH_REQUEST_RETRIES`
- `PETROVICH_BACKOFF_BASE_SECONDS`
- `PETROVICH_MIN_EXPECTED_PRODUCTS`
