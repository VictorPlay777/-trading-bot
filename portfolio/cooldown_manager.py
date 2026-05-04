from datetime import datetime, timedelta


class CooldownManager:
    def __init__(self):
        self.symbol_until = {}
        self.global_until = None
        self.loss_streak = 0

    def set_symbol_cooldown(self, symbol: str, minutes: int):
        self.symbol_until[symbol] = datetime.utcnow() + timedelta(minutes=minutes)

    def set_global_cooldown(self, minutes: int):
        self.global_until = datetime.utcnow() + timedelta(minutes=minutes)

    def allow(self, symbol: str):
        now = datetime.utcnow()
        if self.global_until and now < self.global_until:
            return False
        if symbol in self.symbol_until and now < self.symbol_until[symbol]:
            return False
        return True

