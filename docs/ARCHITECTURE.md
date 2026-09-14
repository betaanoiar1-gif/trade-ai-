# Architecture

`Public Crypto APIs -> Data Quality -> Quant/TA Engine -> Trader Evidence -> One Crypto Trader AI -> Deterministic Risk Firewall -> Paper Broker -> SQLite State/Journal -> Dashboard`

## Trader doctrine
1. Establish market/regime context.
2. Inspect 1D -> 4H -> 1H -> 15M -> 5M hierarchy.
3. Evaluate trend, support/resistance, structure, price action, momentum and volume.
4. Add derivatives context: funding and open interest; other derivatives are optional only when a verified public source is available.
5. Treat liquidity/SMC concepts as hypotheses, never guaranteed signals.
6. Evaluate volatility, volume profile and Fibonacci context.
7. Build primary/alternative scenarios with explicit invalidation.
8. Only then produce LONG/SHORT/HOLD/WAIT/NO_TRADE.
9. The risk firewall independently validates size, leverage, exposure and stop/target logic.
10. The paper broker applies fees, slippage, funding support and conservative liquidation checks.

## AI boundary
The AI interprets evidence and proposes a plan. It does not calculate raw indicators, invent unavailable data, size positions, or bypass risk controls.

## Free-data policy
Public endpoints are preferred. Missing or failed data is marked unavailable; it is never replaced with synthetic zeros. The base project has no paid-data requirement.

## Persistence
SQLite stores decisions, trades, paper account and open positions so a Colab/local restart can restore state. For Colab, the SQLite file should be placed on persistent Google Drive storage.

## Explicit non-goals
No strategy generation/evolution, no multi-agent debate system, no fake metrics, no hidden look-ahead, no forced trade frequency, and no real-money exchange execution.
