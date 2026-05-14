# Bybit ML Bot

Алгоритмический торговый бот для фьючерсов Bybit на основе технических индикаторов и машинного обучения.  
Поддерживает **два режима работы**:  
- **Тестовый (paper trading)** — эмуляция сделок без риска реальных средств.  
- **Реальный (live trading)** — работа через API Bybit с реальными ордерами.  

Имеется встроенный **бэктестер** с учётом комиссий, а также возможность предварительного обучения модели на исторических данных.

---

## 📂 Структура проекта

```
bybit_ml_bot/
├── backtester/         # Модуль для тестирования стратегий на исторических данных
│   ├── backtest.py     # Логика симуляции сделок, TP/SL по ATR, комиссии, риск-менеджмент
│   └── metrics.py      # Подсчёт метрик и сводной статистики по результатам
├── ml/                 # Машинное обучение
│   ├── features.py     # Извлечение 20 техиндикаторов (EMA, RSI, Stoch, MACD, BB, ATR, ADX, CCI, MFI, OBV и др.)
│   ├── labeler.py      # Разметка будущего движения (класс: -1, 0, +1) по горизонту и ATR-порогу
│   └── model.py        # Логистическая регрессия SGD + StandardScaler; сохранение/загрузка модели
├── storage/            # Работа с базой данных SQLite
│   └── db.py           # ORM-модели: Order, Trade, Equity, State; инициализация сессии
├── trader/             # Логика онлайновой торговли
│   ├── exchange.py     # Обёртка CCXT для Bybit (testnet/mainnet), загрузка OHLCV и рыночные ордера
│   ├── broker.py       # Вход по рынку (hook для расширения до OCO TP/SL)
│   ├── risk.py         # Позиционирование по ATR и доле риска
│   └── state.py        # KV-хранилище состояния в БД (восстановление после перезапуска)
├── scripts/            # Утилиты
│   ├── preload_data.py # Быстрый просмотр структуры CSV
│   └── train_offline.py# Предобучение модели на истории
├── utils/              # Вспомогательные утилиты
│   ├── logging.py      # Инициализация логов (Loguru)
│   └── timeframes.py   # Хелперы по таймфреймам
├── docker/Dockerfile   # Контейнер для запуска на сервере
├── config.example.yaml # Шаблон конфигурации
├── run_backtest.py     # Запуск бэктеста на CSV
├── run_paper.py        # Бумажная торговля (эмуляция, без реальных ордеров)
├── run_live.py         # Реальная торговля (через CCXT → Bybit)
└── requirements.txt    # Зависимости
```

---

## ⚙️ Установка

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

В `config.yaml` укажите:
- `symbol`, `timeframe` — торговый инструмент и таймфрейм (например, `BTCUSDT`, `1h`).
- Параметры риска: `risk_per_trade`, `tp_atr_mult`, `sl_atr_mult`, `prob_threshold`.
- Комиссии: `maker_fee`, `taker_fee`.
- Пути: `paths.db_url`, `paths.models_dir`, `paths.logs_dir`.

Укажите свои ключи в `.env`:
 - `BYBIT_API_KEY=ваш_ключ`
 - `BYBIT_API_SECRET=ваш_секрет`
 - `MODE=paper`

---

## 📊 Предварительное обучение модели

Обучите модель на исторических данных перед запуском бота:

```bash
python scripts/train_offline.py --config config.yaml --csv data/BTCUSDT_1h.csv --symbol BTCUSDT --timeframe 1h
```

Требуемый CSV-формат:
```
time,open,high,low,close,volume
```
- `time` — ISO или UNIX ms; в коде будет преобразован в индекс времени.

Модель сохраняется в `models/model_<SYMBOL>_<TF>.joblib` и автоматически подхватывается `run_paper.py`/`run_live.py`.

---

## 🔍 Бэктестирование на исторических данных

Запустите бэктест с учётом комиссий и риск-менеджмента:

```bash
python run_backtest.py --config config.yaml --csv data/BTCUSDT_1h.csv
```

Что делает бэктестер (`backtester/backtest.py`):
- Формирует фичи (20 индикаторов) → `ml/features.py`.
- Размечает цель `y ∈ {-1,0,1}` по горизонту `horizon_bars` и порогу на основе ATR → `ml/labeler.py`.
- Инкрементально обучает модель (SGD логистическая регрессия) на прошлых барах и прогнозирует на текущем.
- Открывает позицию при `p(up)` или `p(down)` ≥ `prob_threshold`.
- Рассчитывает **TP/SL** как множители ATR, PnL с **учётом комиссий** (`taker_fee`/`maker_fee`).
- Ведёт эмуляцию до срабатывания TP/SL или таймаута по барам.

Результаты сохраняются в `storage/`:
- `trades_<symbol>_<tf>.csv` — список сделок (время входа/выхода, PnL, комиссии).
- `equity_<symbol>_<tf>.csv` — кривая капитала.
- Также записи дублируются в SQLite (`paths.db_url`).

---

## 📝 Режимы работы

### 1) Бумажная торговля (эмуляция)
```bash
python run_paper.py --config config.yaml --resume
```
- Подтягивает последнюю модель, если она есть.
- Обновляет модель инкрементально по мере поступления баров.
- Сохраняет сделки и equity в БД; ключ `paper_state` позволяет резюмировать.

### 2) Реальная торговля
```bash
python run_live.py --config config.yaml --resume
```
- Использует CCXT для отправки рыночных ордеров на Bybit.
- **Рекомендуется** начинать с `testnet: true` и малыми объёмами.

---

## 💾 База данных и возобновление работы

- SQLite по адресу из `paths.db_url` (по умолчанию `sqlite:///storage/trading.db`).  
- Таблицы: `orders`, `trades`, `equity`, `state` (KV для резюма).
- Перезапуск с `--resume` восстанавливает капитал из `state`.

---

## ⚖️ Риск-менеджмент и комиссии

- Размер позиции = `(equity * risk_per_trade) / (SL_ATR)`.  
- `SL_ATR = sl_atr_mult × ATR`, `TP_ATR = tp_atr_mult × ATR`.  
- Комиссии учитываются при входе и выходе; влияяют на итоговый PnL.

---

## 🖥️ Сервер и Docker

**Минимум:** 2 vCPU, 4 GB RAM, 20 GB SSD, Python 3.10+.  
Docker:
```bash
docker build -t bybit-ml-bot -f docker/Dockerfile .
docker run -it --rm -v $PWD:/app -w /app bybit-ml-bot python run_backtest.py --config config.yaml --csv data/BTCUSDT_1h.csv
```

---

## 🔮 Дальнейшие улучшения

- Нативные OCO TP/SL ордера Bybit.
- Учёт funding rate и проскальзывания.
- Веб-панель мониторинга и алерты.
- Walk-forward оптимизация параметров и подбор `prob_threshold`.


## 🚀 Запуск обучения и бэктеста

После подготовки данных можно запустить тренировку или бэктест двумя способами:

### Обучение модели
```bash
# вариант 1: запуск напрямую
python scripts/train_offline.py --config config.yaml --csv data/BTCUSDT_1h.csv --symbol BTCUSDT --timeframe 1h

# вариант 2: запуск через пакет
python -m scripts.train_offline --config config.yaml --csv data/BTCUSDT_1h.csv --symbol BTCUSDT --timeframe 1h
```

### Бэктест стратегии
```bash
# вариант 1: запуск напрямую
python run_backtest.py --config config.yaml --csv data/BTCUSDT_1h.csv --symbol BTCUSDT --timeframe 1h

# вариант 2: запуск через пакет
python -m run_backtest --config config.yaml --csv data/BTCUSDT_1h.csv --symbol BTCUSDT --timeframe 1h
```


## 📊 Исторические данные

Для подгрузки котировок с Bybit в CSV используйте скрипт:

```bash
python scripts/preload_data.py --symbol BTCUSDT --timeframe 1h --start 2023-01-01 --end 2023-12-31
```

Параметры:
- `--symbol` — торговая пара (например, BTCUSDT)
- `--timeframe` — таймфрейм (1h, 15m, 1d)
- `--start` — начальная дата (формат YYYY-MM-DD)
- `--end` — конечная дата (формат YYYY-MM-DD)

После этого файл можно использовать в `train_offline.py` и `run_backtest.py`.

---

## 📝 Changelog

- **v0.1**: Создана структура проекта, добавлены базовые модули (бот, стратегия, бэктест, обучение).
- **v0.2**: Добавлен скрипт `preload_data.py` для скачивания исторических данных с Bybit.
- **v0.2.1**: README расширен инструкциями по загрузке истории и запуску бэктеста/обучения.
