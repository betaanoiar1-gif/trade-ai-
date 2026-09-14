# Crypto AI Trader

A crypto-only, tool-using AI trader designed around **evidence first, deterministic risk controls and realistic paper execution**.

## What it does

- Free/public market-data adapters for Binance, Bybit and Deribit.
- Local technical computation: EMA/SMA, RSI, ATR, ADX, MACD, Bollinger Bands, VWAP, relative volume and volume z-score.
- Multi-timeframe context: 1D, 4H, 1H, 15M and 5M.
- Market structure, regime detection, Fibonacci and volume-profile context.
- Order-book depth metrics plus funding/open-interest context when public data is available.
- One AI trader brain through any OpenAI-compatible gateway.
- Strict JSON decision validation; invalid AI output becomes `NO_TRADE` rather than an invented trade.
- Deterministic risk firewall: risk/trade, daily loss, portfolio exposure, leverage and stop/target validation.
- Paper perpetual broker with fees, slippage, funding support, stop/TP and conservative liquidation checks.
- SQLite persistence for decisions, trades, paper account and positions.
- Streamlit dashboard and Colab bootstrap.
- No real exchange-order execution is implemented.

## AI configuration

Set environment variables:

```text
AI_BASE_URL=https://your-openai-compatible-provider/v1
AI_API_KEY=your_key
AI_MODEL=your_model
```

The key is read server-side only; it is not part of the dashboard.

## Run locally

```bash
pip install -e '.[dev]'
streamlit run dashboard/app.py
```

## Colab

Run `notebooks/colab_bootstrap.py`, then configure the three AI environment variables and launch Streamlit. For persistent Colab state, place `data/trader.sqlite3` on Google Drive or another persistent mounted path.

## Safety model

The AI proposes a trade plan; it cannot override deterministic risk controls. Missing data is represented as unavailable. The system is deliberately allowed to wait or refuse a trade. Paper results are simulations and are not evidence of future profitability.
