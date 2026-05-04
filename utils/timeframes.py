def to_ccxt_tf(tf: str) -> str:
    m = {"1m":"1m","3m":"3m","5m":"5m","15m":"15m","30m":"30m","1h":"1h","2h":"2h","4h":"4h","6h":"6h","12h":"12h","1d":"1d"}
    return m.get(tf, tf)
def tf_to_ms(tf: str) -> int:
    num = int(''.join([c for c in tf if c.isdigit()]))
    unit = ''.join([c for c in tf if c.isalpha()])
    if unit=='m': return num*60*1000
    if unit=='h': return num*60*60*1000
    if unit=='d': return num*24*60*60*1000
    raise ValueError(f'Unknown timeframe: {tf}')
