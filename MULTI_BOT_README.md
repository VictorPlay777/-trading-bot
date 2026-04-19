# 🤖 Multi-Bot Trading System

Управляйте несколькими торговыми ботами из одного дашборда! Каждый бот имеет:
- Изолированные API ключи (разные аккаунты)
- Собственную стратегию и риск-настройки
- Независимые логи и статистику
- Горячую перезагрузку конфига

## 📁 Структура

```
bot_configs/          # Конфигурации ботов (JSON)
  ├─ bot_1_aggressive.json
  ├─ bot_2_conservative.json
  └─ bot_3_alts_only.json

bot_logs/             # Логи каждого бота отдельно
  ├─ bot_1_aggressive.log
  └─ ...

bot_data/             # Данные ботов (статистика, кэш)
```

## 🚀 Быстрый старт

### 1. Настрой API ключи в `.env`:
```bash
# Бот 1 - Агрессивный (основной аккаунт)
BYBIT_API_KEY_1=your_key_here
BYBIT_API_SECRET_1=your_secret_here

# Бот 2 - Консервативный (тестовый)
BYBIT_API_KEY_2=testnet_key
BYBIT_API_SECRET_2=testnet_secret

# Бот 3 - Альты (другой аккаунт)
BYBIT_API_KEY_3=another_key
BYBIT_API_SECRET_3=another_secret
```

### 2. Запусти multi-bot систему:
```bash
python run_multi_bot.py
```

### 3. Открой дашборд:
```
http://localhost:5001
```

## 🎛️ Управление ботами

### Через Web Dashboard:
- **Start/Stop** - Запуск и остановка
- **Pause/Resume** - Пауза (позиции сохраняются)
- **Edit** - Изменение настроек (hot-reload)
- **Compare** - Сравнение performance

### Через API:
```bash
# Список ботов
curl http://localhost:5001/api/bots

# Запустить бота
curl -X POST http://localhost:5001/api/bots/bot_1_aggressive/start

# Остановить бота
curl -X POST http://localhost:5001/api/bots/bot_1_aggressive/stop

# Обновить конфиг
curl -X PUT http://localhost:5001/api/bots/bot_1_aggressive \
  -H "Content-Type: application/json" \
  -d '{"strategy": {"leverage": 50}}'

# Логи бота
curl http://localhost:5001/api/bots/bot_1_aggressive/logs?lines=50
```

## 📊 Примеры конфигураций

### Aggressive (Высокий риск)
```json
{
  "name": "Aggressive High-Leverage",
  "strategy": {
    "leverage": 100,
    "max_positions": 50,
    "probe_enabled": true,
    "pyramiding_enabled": true
  },
  "risk": {
    "stop_loss_pct": 1.0,
    "take_profit_pct": 3.0,
    "max_drawdown_pct": 30
  }
}
```

### Conservative (Безопасный)
```json
{
  "name": "Conservative Safe-Play",
  "strategy": {
    "leverage": 10,
    "max_positions": 20,
    "probe_enabled": false
  },
  "risk": {
    "stop_loss_pct": 0.5,
    "take_profit_pct": 1.5,
    "max_drawdown_pct": 10
  }
}
```

### Alts Specialist (Только альты)
```json
{
  "name": "Alts Specialist",
  "strategy": {
    "symbols_whitelist": ["SOLUSDT", "AVAXUSDT", "LINKUSDT"],
    "leverage": 50
  },
  "filters": {
    "blocked_symbols": ["BTCUSDT", "ETHUSDT"]
  }
}
```

## 🔄 Hot-Reload Config

Изменения в `bot_configs/*.json` применяются автоматически без перезапуска бота!

Поддерживается:
- ✅ Leverage
- ✅ Max positions
- ✅ Risk parameters
- ⚠️ API keys (требуется перезапуск)

## 🛡️ Безопасность

- Каждый бот работает в своём потоке
- Изолированные API ключи
- Отдельные лог-файлы
- Testnet по умолчанию для новых ботов

## 📈 Performance Leaderboard

Система автоматически ранжирует ботов по composite score:
- PnL (40%)
- Win Rate (30%)
- Profit Factor (20%)
- Drawdown (10%)

## ⚠️ Важно!

- Старый `main_new.py` работает независимо
- Multi-bot использует порт **5001** (не 5000)
- Каждый бот = отдельный процесс

## 🆘 Troubleshooting

**Бот не запускается:**
```bash
# Проверь API ключи
echo $BYBIT_API_KEY_1

# Проверь логи
cat bot_logs/bot_1_aggressive.log
```

**Порт 5001 занят:**
```bash
# Измени порт в run_multi_bot.py
start_dashboard(port=5002)
```

## 📦 Файлы системы

| Файл | Описание |
|------|----------|
| `run_multi_bot.py` | Главный launcher |
| `bot_manager.py` | Оркестратор ботов |
| `bot_instance.py` | Класс одного бота |
| `multi_bot_dashboard.py` | Web UI (порт 5001) |
| `bot_configs/*.json` | Конфиги ботов |

---

**Текущий бот продолжает работать!** Эта система не трогает существующий `main_new.py`.
