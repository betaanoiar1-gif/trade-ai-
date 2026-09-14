from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series: return s.ewm(span=n, adjust=False).mean()
def sma(s: pd.Series, n: int) -> pd.Series: return s.rolling(n).mean()

def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff(); up = d.clip(lower=0); dn = -d.clip(upper=0)
    rs = up.ewm(alpha=1/n, adjust=False).mean() / dn.ewm(alpha=1/n, adjust=False).mean().replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df.close.shift(1)
    tr = pd.concat([(df.high-df.low), (df.high-prev).abs(), (df.low-prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()

def macd(close: pd.Series, fast: int=12, slow: int=26, signal: int=9):
    line = ema(close, fast)-ema(close, slow); sig = ema(line, signal)
    return line, sig, line-sig

def bollinger(close: pd.Series, n: int=20, k: float=2.0):
    mid=sma(close,n); sd=close.rolling(n).std(); return mid, mid+k*sd, mid-k*sd

def adx(df: pd.DataFrame, n: int=14) -> pd.Series:
    up=df.high.diff(); down=-df.low.diff()
    plus=np.where((up>down)&(up>0),up,0.0); minus=np.where((down>up)&(down>0),down,0.0)
    a=atr(df,n); p=100*pd.Series(plus,index=df.index).ewm(alpha=1/n,adjust=False).mean()/a
    m=100*pd.Series(minus,index=df.index).ewm(alpha=1/n,adjust=False).mean()/a
    dx=100*(p-m).abs()/(p+m).replace(0,np.nan); return dx.ewm(alpha=1/n,adjust=False).mean()

def vwap(df: pd.DataFrame) -> pd.Series:
    tp=(df.high+df.low+df.close)/3; return (tp*df.volume).cumsum()/df.volume.cumsum().replace(0,np.nan)

def zscore(s: pd.Series, n: int=50) -> pd.Series:
    m=s.rolling(n).mean(); sd=s.rolling(n).std(); return (s-m)/sd.replace(0,np.nan)

def relative_volume(df: pd.DataFrame, n: int=20) -> pd.Series: return df.volume / df.volume.rolling(n).mean()

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    x=df.copy(); x["ema20"]=ema(x.close,20); x["ema50"]=ema(x.close,50); x["ema200"]=ema(x.close,200)
    x["rsi14"]=rsi(x.close); x["atr14"]=atr(x); x["adx14"]=adx(x); x["vwap"]=vwap(x)
    x["macd"],x["macd_signal"],x["macd_hist"]=macd(x.close)
    x["bb_mid"],x["bb_high"],x["bb_low"]=bollinger(x.close); x["rel_volume"]=relative_volume(x); x["volume_z"]=zscore(x.volume)
    return x

@dataclass(frozen=True)
class Structure:
    trend: str
    last_high: float | None
    last_low: float | None
    bos: str | None
    choch: str | None

def market_structure(df: pd.DataFrame, lookback: int=5) -> Structure:
    x=df.tail(max(lookback*20, 100)); highs=x.high.rolling(lookback,center=True).max(); lows=x.low.rolling(lookback,center=True).min()
    ph=x.high[ x.high.eq(highs) ].dropna(); pl=x.low[ x.low.eq(lows) ].dropna()
    trend="range"
    if len(ph)>=2 and len(pl)>=2:
        if ph.iloc[-1]>ph.iloc[-2] and pl.iloc[-1]>pl.iloc[-2]: trend="bullish"
        elif ph.iloc[-1]<ph.iloc[-2] and pl.iloc[-1]<pl.iloc[-2]: trend="bearish"
    return Structure(trend, float(ph.iloc[-1]) if len(ph) else None, float(pl.iloc[-1]) if len(pl) else None, None, None)
