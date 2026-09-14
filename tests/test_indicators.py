import pandas as pd
from crypto_trader.indicators import rsi, atr, enrich

def sample():
    n=250; x=pd.Series(range(n),dtype=float); return pd.DataFrame({'open':x,'high':x+1,'low':x-1,'close':x+.5,'volume':100.0})

def test_rsi_bounds():
    s=rsi(sample().close).dropna(); assert ((s>=0)&(s<=100)).all()

def test_atr_positive(): assert (atr(sample()).dropna()>0).all()

def test_enrich_columns():
    x=enrich(sample()); assert {'ema20','ema50','rsi14','atr14','macd','vwap'}.issubset(x.columns)
