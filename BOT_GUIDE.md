# 🤖 Trading Bot Guide

## 🚀 Запуск бота

### 1. Загрузить файлы на сервер
```bash
cd c:\!trading-bot
scp temp_bot/scanner.py svy1990@111.88.150.44:~/-trading-bot/ml_bot/
scp temp_bot/trader/exchange_demo.py svy1990@111.88.150.44:~/-trading-bot/ml_bot/trader/
```

### 2. Подключиться к серверу
```bash
ssh svy1990@111.88.150.44
```

### 3. Запустить бота
```bash
cd ~/-trading-bot/ml_bot
source venv/bin/activate

# Остановить старый процесс
pkill -f "python3 scanner.py"

# Запустить новый
nohup python3 scanner.py --config config_scanner.yaml --top 9999 --size 10000 > ml_live_scanner.log 2>&1 &

# Проверить статус
ps aux | grep scanner.py
```

## 📊 Просмотр логов онлайн

### Все логи в реальном времени
```bash
tail -f ml_live_scanner.log
```

### Только открытия и закрытия
```bash
tail -f ml_live_scanner.log | grep -E "OPENED|TP|Closed|EARLY"
```

### Только сигналы
```bash
tail -f ml_live_scanner.log | grep "signal="
```

### Последние 10 сигналов
```bash
grep "signal=" ml_live_scanner.log | tail -10
```

## 🛠 Полезные команды

### Проверить открытые позиции
```bash
python3 -c "
from trader.exchange_demo import Exchange
import yaml
cfg = yaml.safe_load(open('config_scanner.yaml'))
ex = Exchange(cfg)
pos = ex.get_positions()
if pos.get('retCode') == 0:
    positions = pos.get('result', {}).get('list', [])
    print(f'Positions: {len(positions)}')
    for p in positions[:5]:
        print(f\"  {p.get('symbol')}: {p.get('side')} {p.get('size')} @ {p.get('avgPrice')}\")"
```

### Выставить TP на все позиции
```bash
python3 set_tp_all.py
```

### Проверить TP ордера
```bash
python3 -c "
from trader.exchange_demo import Exchange
import yaml
cfg = yaml.safe_load(open('config_scanner.yaml'))
ex = Exchange(cfg)
orders = ex._request('GET', '/v5/order/realtime', {'category': 'linear', 'openOnly': 1}, auth=True)
if orders.get('retCode') == 0:
    order_list = orders.get('result', {}).get('list', [])
    print(f'TP orders: {len(order_list)}')
    for o in order_list[:5]:
        print(f\"  {o.get('symbol')}: {o.get('side')} @ {o.get('price')}\")"
```

## 📈 Статистика

### Winrate закрытых сделок
```bash
grep "Closed.*TP" ml_live_scanner.log | wc -l
grep ">> OPENED" ml_live_scanner.log | wc -l
```

### Прибыль/убыток
```bash
grep "Equity:" ml_live_scanner.log | tail -5
```

## 🔄 Перезапуск бота

```bash
cd ~/-trading-bot/ml_bot
pkill -f "python3 scanner.py"
source venv/bin/activate
nohup python3 scanner.py --config config_scanner.yaml --top 9999 --size 10000 > ml_live_scanner.log 2>&1 &
```

## 📱 Для Windows (без SSH разрывов)

Используй `screen`:
```bash
ssh svy1990@111.88.150.44
screen -S bot
cd ~/-trading-bot/ml_bot
source venv/bin/activate
tail -f ml_live_scanner.log | grep -E "OPENED|TP|signal="
# Отключиться: Ctrl+A, потом D
```

## ⚙️ Текущие настройки

- **Таймфрейм**: 15m
- **Порог вероятности**: 0.68 (68%)
- **TP**: 0.5% (лимитный ордер)
- **Плечо**: 1x
- **Размер позиции**: 10000 USDT
- **Проверка позиций**: каждые 5 секунд

## 🎯 Стратегия

1. **Сканирование** каждые 15 минут
2. **ML модель** предсказывает направление
3. **Открытие** по рыночной цене
4. **TP ордер** выставляется сразу на бирже
5. **Early exit** при развороте тренда и убытке >2%

---
*Бот работает 24/7, все автоматизировано!*
