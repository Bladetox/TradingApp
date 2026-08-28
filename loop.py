"""
Minimal self-improving trading loop.

Each run:
  1. GENERATE : load current strategy config
  2. Fetch data (yfinance)
  3. Backtest the strategy (MA crossover + RSI filter)
  4. VERIFY   : compute expectancy, profit factor, max drawdown, trade count
  5. LOG      : append the run + metrics to runs.json (persistent state)
  6. UPDATE   : if the strategy is bad on simple rules, tweak config.json for next run

Run it again and again (manually, or on a schedule) and config.json evolves.
No paid tools, no external DB. Everything lives in this folder.
"""

import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf

DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(DIR, "config.json")
RUNS_PATH = os.path.join(DIR, "runs.json")  # local fallback if Supabase isn't reachable

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://otbaaunfywxixuzsdwrv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")  # set this as an env var, don't hardcode it

# ---------- 1. GENERATE (load current strategy) ----------

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ---------- data + indicators ----------

def fetch_data(cfg):
    df = yf.download(
        cfg["symbol"], period=cfg["period"], interval=cfg["interval"],
        progress=False, auto_adjust=True,
    )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    return df


def add_indicators(df, cfg):
    df = df.copy()
    df["ma_fast"] = df["Close"].rolling(cfg["ma_fast"]).mean()
    df["ma_slow"] = df["Close"].rolling(cfg["ma_slow"]).mean()

    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(cfg["rsi_period"]).mean()
    loss = (-delta.clip(upper=0)).rolling(cfg["rsi_period"]).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    return df.dropna()


# ---------- 3. VERIFY (backtest engine, independent of the generator) ----------

def backtest(df, cfg):
    """Long-only: enter when fast MA crosses above slow MA and RSI < threshold.
    Exit on stop-loss, take-profit, or MA crossing back down."""
    trades = []
    in_position = False
    entry_price = 0.0

    for i in range(1, len(df)):
        row, prev = df.iloc[i], df.iloc[i - 1]
        crossed_up = prev["ma_fast"] <= prev["ma_slow"] and row["ma_fast"] > row["ma_slow"]
        crossed_down = prev["ma_fast"] >= prev["ma_slow"] and row["ma_fast"] < row["ma_slow"]

        if not in_position and crossed_up and row["rsi"] < cfg["rsi_buy_below"]:
            in_position = True
            entry_price = float(row["Close"])
            entry_date = df.index[i]
            continue

        if in_position:
            price = float(row["Close"])
            change = (price - entry_price) / entry_price
            hit_stop = change <= -cfg["stop_loss_pct"]
            hit_target = change >= cfg["take_profit_pct"]

            if hit_stop or hit_target or crossed_down:
                trades.append({
                    "entry_date": str(entry_date.date()),
                    "exit_date": str(df.index[i].date()),
                    "entry_price": entry_price,
                    "exit_price": price,
                    "pnl_pct": change * 100,
                })
                in_position = False

    return trades


def score(trades):
    if not trades:
        return {
            "num_trades": 0, "win_rate": 0, "expectancy_pct": 0,
            "profit_factor": 0, "max_drawdown_pct": 0,
        }

    pnls = [t["pnl_pct"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = len(wins) / len(pnls) * 100
    avg_win = np.mean(wins) if wins else 0
    avg_loss = np.mean(losses) if losses else 0
    expectancy = (len(wins) / len(pnls)) * avg_win + (len(losses) / len(pnls)) * avg_loss

    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0.0001
    profit_factor = gross_profit / gross_loss

    equity = np.cumsum(pnls)
    peak = np.maximum.accumulate(equity)
    drawdown = equity - peak
    max_dd = float(drawdown.min())

    return {
        "num_trades": len(pnls),
        "win_rate": round(win_rate, 2),
        "expectancy_pct": round(float(expectancy), 3),
        "profit_factor": round(float(profit_factor), 2),
        "max_drawdown_pct": round(max_dd, 2),
    }


# ---------- 4/5. LOG (persistent state) ----------

def load_runs_local():
    if os.path.exists(RUNS_PATH):
        with open(RUNS_PATH) as f:
            return json.load(f)
    return []


def log_run_local(cfg, metrics, trades):
    runs = load_runs_local()
    runs.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": cfg,
        "metrics": metrics,
        "trades": trades,
    })
    with open(RUNS_PATH, "w") as f:
        json.dump(runs, f, indent=2)
    return len(runs)


def log_run_supabase(cfg, metrics, trades):
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/runs",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        json={"config": cfg, "metrics": metrics, "trades": trades},
        timeout=10,
    )
    resp.raise_for_status()


def log_run(cfg, metrics, trades):
    """Log to Supabase if a key is configured, otherwise fall back to runs.json."""
    if SUPABASE_KEY:
        try:
            log_run_supabase(cfg, metrics, trades)
            return "supabase"
        except Exception as e:
            print(f"Supabase logging failed ({e}), falling back to runs.json")

    count = log_run_local(cfg, metrics, trades)
    return f"runs.json (run #{count})"


# ---------- 6. UPDATE (the rule that changes config.json for next run) ----------

def update_config(cfg, metrics):
    """Simple, explainable rules. No magic, no ML yet."""
    new_cfg = dict(cfg)
    notes = []

    if metrics["num_trades"] < 5:
        new_cfg["rsi_buy_below"] = min(cfg["rsi_buy_below"] + 5, 70)
        notes.append("Too few trades -> loosened RSI filter")

    elif metrics["expectancy_pct"] < 0:
        new_cfg["ma_fast"] = cfg["ma_fast"] + 5
        new_cfg["ma_slow"] = cfg["ma_slow"] + 10
        notes.append("Negative expectancy -> widened MA windows (slower, fewer false signals)")

    elif metrics["max_drawdown_pct"] < -10:
        new_cfg["stop_loss_pct"] = max(cfg["stop_loss_pct"] - 0.005, 0.005)
        notes.append("Drawdown too deep -> tightened stop-loss")

    elif metrics["profit_factor"] < 1.5:
        new_cfg["take_profit_pct"] = cfg["take_profit_pct"] + 0.01
        notes.append("Profit factor weak -> let winners run further")

    else:
        notes.append("Strategy meets baseline thresholds -> no change this run")

    return new_cfg, notes


# ---------- orchestration ----------

def main():
    cfg = load_config()
    print(f"Loaded config: {cfg}\n")

    df = fetch_data(cfg)
    df = add_indicators(df, cfg)
    trades = backtest(df, cfg)
    metrics = score(trades)

    print("Metrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    destination = log_run(cfg, metrics, trades)
    print(f"\nLogged run to {destination}")

    new_cfg, notes = update_config(cfg, metrics)
    print("\nUpdate rule decision:")
    for n in notes:
        print(f"  - {n}")

    if new_cfg != cfg:
        save_config(new_cfg)
        print(f"\nconfig.json updated for next run: {new_cfg}")
    else:
        print("\nconfig.json unchanged.")


if __name__ == "__main__":
    main()
