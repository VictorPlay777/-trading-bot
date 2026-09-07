# Панель управления торговым ботом

## Архитектура

Панель добавлена поверх существующего торгового движка и не заменяет расчёт
сигналов или биржевой слой:

```text
React/Vite панель
        │ HTTP + SSE
        ▼
FastAPI backend ───────► SQLite dashboard store
        │
        ▼
ProcessManager ────────► selective_ml_bot.py
        │
        ▼
      Bybit
```

Backend запускается как отдельный процесс и сам создаёт, останавливает и
супервизирует процесс бота. При `BOT_AUTO_RESTART=true` падение дочернего
процесса приводит к его повторному запуску. Поэтому на сервере этот backend
заменяет `run_selective_ml_forever.sh`; одновременно запускать оба
супервизора нельзя.

## Локальный запуск

Из корня репозитория:

```bash
export DASHBOARD_PASSWORD='change-me'
export DASHBOARD_SECRET='change-this-session-secret'
export BOT_AUTO_RESTART=true
venv/bin/python -m uvicorn dashboard.backend.app:app \
  --host 127.0.0.1 --port 8080
```

Собранный frontend обслуживается backend по адресу
`http://127.0.0.1:8080/`. Для разработки frontend в отдельном терминале:

```bash
cd dashboard/frontend
npm ci
npm run dev
```

После запуска откройте `http://127.0.0.1:8080/` и войдите с пользователем и
паролем из переменных окружения. Backend слушает только localhost в примере
выше.

## Переменные окружения

| Переменная | Назначение |
| --- | --- |
| `DASHBOARD_PASSWORD` | Пароль входа в панель. |
| `DASHBOARD_USERNAME` | Имя пользователя; по умолчанию `admin`. |
| `DASHBOARD_SECRET` | Секрет подписания сессий; задайте постоянное значение. |
| `DASHBOARD_DB_PATH` | Путь к SQLite store; по умолчанию `data/dashboard.db`. |
| `BOT_CONFIG_PATH` | YAML-конфигурация бота; по умолчанию `config_scanner.yaml`. |
| `BOT_PYTHON` | Интерпретатор дочернего бота; по умолчанию текущий Python. |
| `BOT_LOG_PATH` | Файл stdout/stderr дочернего бота. |
| `BOT_AUTO_RESTART` | Перезапускать бота после выхода; по умолчанию `true`. |
| `DASHBOARD_COOKIE_SECURE` | Ставить Secure на cookie; включите за HTTPS. |
| `BYBIT_API_KEY` | API key Bybit для backend/бота. |
| `BYBIT_API_SECRET` | API secret Bybit для backend/бота. |

Не храните `.env` в git и не используйте API-ключи с лишними правами.

## Импорт истории

Импорт JSONL/CSV истории в dashboard store выполняется из корня репозитория:

```bash
venv/bin/python -m dashboard.import_history
```

Перед импортом проверьте `DASHBOARD_DB_PATH` и входные файлы, используемые
импортером. Повторный импорт рассчитан на идемпотентную загрузку по
идентификаторам сделок/fills.

## Деплой на Ubuntu

### 1. Подготовить код и окружение

На сервере:

```bash
cd /home/user1/trading-bot
git pull origin devin/1788791207-web-dashboard
chmod +x deploy/install.sh deploy/build_frontend.sh
```

Создайте `/home/user1/trading-bot/.env` с production-значениями, включая
`DASHBOARD_PASSWORD`, постоянный `DASHBOARD_SECRET`, пути бота и ключи Bybit.
Файл должен быть доступен пользователю `user1` и не должен попадать в git.

### 2. Установить systemd unit

```bash
cd /home/user1/trading-bot
./deploy/install.sh
sudo systemctl start trading-dashboard.service
sudo systemctl status trading-dashboard.service
```

Unit использует:

```text
User=user1
WorkingDirectory=/home/user1/trading-bot
EnvironmentFile=/home/user1/trading-bot/.env
```

Backend слушает `127.0.0.1:8080`. Логи доступны через
`journalctl -u trading-dashboard.service`.

### 3. Собрать frontend и передать dist

На машине, где установлен Node.js:

```bash
./deploy/build_frontend.sh
rsync -a --delete dashboard/frontend/dist/ \
  user1@host:/home/user1/trading-bot/dashboard/frontend/dist/
```

На сервере после обновления `dist`:

```bash
sudo systemctl restart trading-dashboard.service
```

Серверу Node.js не нужен: backend раздаёт уже собранный `dist`.

### 4. Настроить nginx и HTTPS

Скопируйте `deploy/nginx-dashboard.conf.example` в
`/etc/nginx/sites-available/trading-dashboard`, замените
`dashboard.example.com` и пути сертификатов, затем включите сайт:

```bash
sudo ln -s /etc/nginx/sites-available/trading-dashboard \
  /etc/nginx/sites-enabled/trading-dashboard
sudo nginx -t
sudo systemctl reload nginx
```

В `.env` после включения HTTPS установите
`DASHBOARD_COOKIE_SECURE=true`. Для `/api/stream` в примере уже отключена
буферизация и установлен длинный `proxy_read_timeout`.

### 5. Переход с run_selective_ml_forever.sh

Сначала остановите старый supervisor и убедитесь, что старый процесс бота
не остался запущенным. Затем запустите `trading-dashboard.service` и
нажмите `START` в панели. Не оставляйте `run_selective_ml_forever.sh`
запущенным одновременно с dashboard ProcessManager.

При переходе бот будет перезапущен. На старте он подтянет состояние из
Bybit через exchange-first reconcile; это позволяет восстановить фактические
позиции и не полагаться только на локальную память старого процесса.

## Безопасность

- Используйте длинный уникальный `DASHBOARD_PASSWORD` и постоянный
  `DASHBOARD_SECRET`.
- Открывайте панель через HTTPS/nginx, а не напрямую через порт 8080.
- В firewall не открывайте 8080 наружу; разрешайте только nginx или используйте
  SSH-туннель:

  ```bash
  ssh -L 8080:127.0.0.1:8080 user1@host
  ```

- Ограничьте API-ключи Bybit минимально необходимыми правами.
- Не публикуйте `.env`, SQLite database и логи.

## Известные ограничения

- История equity появляется только с момента установки bridge; старая equity
  history автоматически не восстанавливается.
- Процент drawdown требует equity history.
- Sharpe рассчитывается только при наличии минимум 20 торговых дней.
- Изменения `ProductionConfig` применяются только после рестарта бота.
- SL/TP в панели — внутренние уровни бота, а не биржевые ордера. Они
  применяются в течение `position_loop_interval`.
- Kill switch сам позиции не закрывает. Для закрытия используйте
  `EMERGENCY STOP` с включённой галочкой закрытия позиций.
- `fees_actual` заполняется только для сделок, которым удалось сопоставить
  fills.
