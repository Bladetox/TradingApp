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

### Logging to Supabase (optional)

By default, if no Supabase key is set, runs are logged to a local `runs.json`
file. To log to Supabase instead, set an environment variable before running:

```bash
export SUPABASE_KEY=sb_publishable_xxx
python3 loop.py
```

This requires a `runs` table to already exist in the project (see the SQL
below). The Supabase URL is hardcoded to
`https://otbaaunfywxixuzsdwrv.supabase.co` — change `SUPABASE_URL` at the top
of `loop.py` if you're using a different project.

```sql
create table runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  config jsonb not null,
  metrics jsonb not null,
  trades jsonb not null
);

alter table runs enable row level security;

create policy "allow insert with publishable key"
  on runs for insert to anon with check (true);

create policy "allow read with publishable key"
  on runs for select to anon using (true);
```

Never commit your Supabase key to the repo — always pass it as an env
variable.

## Viewing the ledger (no terminal needed)

`docs/index.html` is a self-contained dashboard that reads the `runs` table
straight from Supabase. Once GitHub Pages is enabled for this repo, it's live
at `https://bladetox.github.io/TradingApp/` — nothing to download or run.

It shows the current strategy config, an expectancy trend across runs, and a
full run ledger with a pass/fail marker per run (expectancy > 0, profit
factor > 1.5, drawdown better than -15%).


## Files

- `config.json` — current strategy parameters (this is what evolves)
- `runs.json` — local run log, used only if `SUPABASE_KEY` isn't set (created on first run)
- `loop.py` — the whole loop

## Notes

- This is paper/backtest only. It does not place real trades.
- The update rule is deliberately simple and readable (a handful of if/else
  checks) so you can see exactly why the config changed each run. No black-box
  ML here yet — that's a later step, once the simple rules prove the loop works.
- Realistic target for a "good" strategy is expectancy > 0 and profit factor
  > 1.5 over 200+ trades, not a 95% win rate (see the doc you started from
  for why that number isn't realistic).
