import json
from storage.db import State
def save_kv(session, key: str, value: dict):
    row = session.query(State).filter_by(key=key).one_or_none()
    if row is None: row = State(key=key, value=json.dumps(value)); session.add(row)
    else: row.value=json.dumps(value)
    session.commit()
def load_kv(session, key: str) -> dict | None:
    row = session.query(State).filter_by(key=key).one_or_none()
    if row is None: return None
    try: return json.loads(row.value)
    except Exception: return None
