import streamlit as st
from crypto_trader.runtime import TradingRuntime

st.set_page_config(page_title="Crypto AI Trader", layout="wide")
st.title("Crypto AI Trader")
st.caption("Crypto-only • public market data • deterministic risk firewall • paper execution")
symbol=st.sidebar.text_input("Symbol","BTCUSDT").upper().strip()
run=st.button("Run trader cycle", type="primary")
if run:
    try:
        result=TradingRuntime(symbol).step(); snap=result.get("snapshot",{}); account=result.get("paper_account",{})
        if not snap: st.error(result.get("reason","No market snapshot")); st.stop()
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Price",f"{snap['price']:.6g}")
        rsi=snap['technical'].get('rsi14'); c2.metric("RSI", "—" if rsi is None else f"{rsi:.2f}")
        c3.metric("Regime",snap['regime']['name'])
        c4.metric("Paper equity",f"{account.get('equity',1000):.2f}")
        st.subheader("AI trader")
        if result.get("plan"): st.json(result["plan"])
        else: st.info(result.get("reason","No executable AI decision"))
        if result.get("risk"): st.subheader("Risk firewall"); st.json(result["risk"])
        a,b=st.columns(2)
        with a: st.subheader("Multi-timeframe"); st.json(snap["multi_timeframe"])
        with b: st.subheader("Order book / derivatives"); st.json({"orderbook":snap["orderbook"],"derivatives":snap["derivatives"]})
        st.subheader("Paper account"); st.json(account)
        st.subheader("Recent decisions"); st.json(TradingRuntime(symbol).trader.state.recent_decisions(10))
    except Exception as e: st.error(f"Data/analysis error: {e}")
else:
    st.info("Configure AI_BASE_URL, AI_API_KEY and AI_MODEL in the environment, then run a cycle. Without AI credentials the system will safely WAIT/NO_TRADE.")
