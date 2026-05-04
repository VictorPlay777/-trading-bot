from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, JSON, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

Base = declarative_base()

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    exchange_id = Column(String)
    symbol = Column(String)
    side = Column(String)
    type = Column(String)
    price = Column(Float)
    amount = Column(Float)
    status = Column(String)
    created_at = Column(DateTime, default=func.now())
    extra = Column(JSON)

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    direction = Column(String)
    entry_time = Column(DateTime)
    exit_time = Column(DateTime)
    entry_price = Column(Float)
    exit_price = Column(Float)
    qty = Column(Float)
    pnl = Column(Float)
    outcome = Column(String)
    fee_paid = Column(Float, default=0.0)

class Equity(Base):
    __tablename__ = "equity"
    id = Column(Integer, primary_key=True)
    time = Column(DateTime, default=func.now())
    equity = Column(Float)

class State(Base):
    __tablename__ = "state"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True)
    value = Column(Text)

def make_session(db_url: str):
    engine = create_engine(db_url, echo=False, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)
