import streamlit as st
from crypto_trader.trader import CryptoTrader

st.set_page_config(page_title="Crypto AI Trader",layout="wide")
st.title("Crypto AI Trader")
st.caption("Crypto-only • free public market data • paper trading")
symbol=st.sidebar.text_input("Symbol","BTCUSDT").upper()
interval=st.sidebar.selectbox("Timeframe",["15m","1h","4h","1d"],index=1)
if st.button("Analyze market",type="primary"):
    try:
        t=CryptoTrader(symbol); snap=t.snapshot(interval)
        c1,c2,c3=st.columns(3); c1.metric("Price",f"{snap['price']:.6g}"); c2.metric("RSI",f"{snap['technical']['rsi14']:.2f}"); c3.metric("Regime",snap['structure']['trend'])
        st.subheader("Technical context"); st.json(snap["technical"])
        st.subheader("Market structure"); st.json(snap["structure"])
        st.subheader("Derivatives"); st.json(snap["derivatives"])
        if t.ai.enabled(): st.subheader("AI Trader decision"); st.json(t.analyze())
        else: st.info("AI gateway is not configured. Deterministic analysis is shown; no decision is fabricated.")
    except Exception as e: st.error(f"Data/analysis error: {e}")
