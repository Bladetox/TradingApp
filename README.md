# Trading Loop (v0)

The smallest possible version of a self-improving trading loop. One script,
one config file, one log file. No database, no cloud, no paid tools.

## How it works

Each time you run `loop.py`:

1. Reads `config.json` (the current strategy's parameters)
2. Pulls stock data with `yfinance`
3. Backtests a simple MA-crossover + RSI strategy
4. Scores it: win rate, expectancy, profit factor, max drawdown
5. Appends the run + metrics to `runs.json` (this is the loop's memory)
6. Applies a simple rule to tweak `config.json` for the next run

Run it again -> it picks up wherever the last run left off, because
`config.json` was already updated.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python3 loop.py
```

## Files

- `config.json` — current strategy parameters (this is what evolves)
- `runs.json` — every run ever logged, with full trade history (created on first run)
- `loop.py` — the whole loop

## Notes

- This is paper/backtest only. It does not place real trades.
- The update rule is deliberately simple and readable (a handful of if/else
  checks) so you can see exactly why the config changed each run. No black-box
  ML here yet — that's a later step, once the simple rules prove the loop works.
- Realistic target for a "good" strategy is expectancy > 0 and profit factor
  > 1.5 over 200+ trades, not a 95% win rate (see the doc you started from
  for why that number isn't realistic).
