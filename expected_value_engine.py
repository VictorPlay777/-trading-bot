class ExpectedValueEngine:
    def __init__(self, taker_fee=0.0006):
        self.taker_fee = taker_fee

    def estimate(self, p_win: float, avg_win: float, avg_loss: float, slippage: float):
        fees = 2.0 * self.taker_fee
        return p_win * avg_win - (1.0 - p_win) * avg_loss - fees - slippage

