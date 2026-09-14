# Architecture

## Runtime
`Public Crypto APIs -> Data Normalizer -> Quant/TA Engine -> Trader Tools -> One Crypto Trader AI -> Deterministic Risk Firewall -> Paper Broker -> Journal/State -> Dashboard`

The AI is an interpreter/decision-maker, not a calculator. Exact indicators, sizing, fees and portfolio constraints are deterministic code.

## Analysis doctrine
1. Establish BTC/market context and regime.
2. Inspect higher timeframe structure before execution timeframe.
3. Evaluate trend, support/resistance, price action, momentum and volume.
4. Add derivatives context: funding, OI, liquidations and basis when available.
5. Evaluate liquidity/SMC concepts as hypotheses, never facts.
6. Check volatility and correlation.
7. Check available crypto news/catalysts.
8. Build primary and alternative scenarios with explicit invalidation.
9. Only then create a trade plan.
10. Risk engine independently validates size/exposure.
11. Paper broker models fees and slippage.

## Free-data policy
Public endpoints are preferred. API adapters must expose freshness and completeness. Missing data becomes `unavailable`, never zero. A provider failure cannot silently become synthetic data.

## Colab resilience
Persistent state must be saved to a durable location/repository artifact before session termination and loaded on startup. The trading engine is idempotent: repeated execution of the same market event cannot duplicate a paper order.

## Explicit non-goals
No strategy generation, strategy mutation/evolution, paid-data dependency, live-money execution, fake metrics, hidden look-ahead, or forced trade frequency.
