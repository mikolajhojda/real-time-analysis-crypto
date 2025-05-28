# RSI.py
"""
Streaming MA-crossover + RSI strategy that always uses a 150-bar window.
Call .update(bar) with each new bar; call .live_stats() any time.
"""

import math, warnings
import numpy as np
import pandas as pd


WINDOW = 150            # ← size of rolling window in bars
RSI_LEN = 14


class MovingAverageRSIStrategy:
    def __init__(self, capital: float, short_period: int, long_period: int):
        # parameters
        self.short_period = short_period
        self.long_period = long_period
        # portfolio state
        self.initial_capital = capital
        self.capital = capital
        self.is_long = False
        self.entry_price = None
        self.equity = [capital]          # realised equity after each SELL
        # data container
        self.data: pd.DataFrame | None = None

    # ─────────────────────────────────────────────────────────── helpers
    def _calc_indicators(self):
        """EMA & RSI computed on self.data (≤ WINDOW rows)."""
        df = self.data
        df["short_ma"] = df["price"].ewm(span=self.short_period).mean()
        df["long_ma"] = df["price"].ewm(span=self.long_period).mean()

        delta = df["price"].diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        gain = up.rolling(RSI_LEN).mean()
        loss = down.rolling(RSI_LEN).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

    # ─────────────────────────────────────────────────────────── public
    def update(self, bar: dict) -> str | None:
        """
        Feed one bar dict (bucket/open/high/low/close/volume).
        Returns 'BUY', 'SELL', or None.
        """
        warnings.filterwarnings("ignore", category=pd.errors.SettingWithCopyWarning)

        ts = pd.to_datetime(bar["bucket"], unit="s")
        new_row = pd.DataFrame({"price": [bar["close"]]}, index=[ts])
        self.data = new_row if self.data is None else pd.concat([self.data, new_row])

        # keep only the last WINDOW rows
        self.data = self.data.tail(WINDOW)

        # need full window before we can act
        if len(self.data) < WINDOW:
            return None

        self._calc_indicators()
        last = self.data.iloc[-1]
        price = bar["close"]

        # decision logic
        if self.is_long and last["short_ma"] < last["long_ma"]:
            # EXIT → realise P&L
            self.capital = price * self.capital / self.entry_price
            self.equity.append(self.capital)
            self.is_long, self.entry_price = False, None
            return "SELL"

        if (
            (not self.is_long)
            and last["short_ma"] > last["long_ma"]
            and last["rsi"] < 30
        ):
            # ENTER
            self.is_long, self.entry_price = True, price
            return "BUY"

        return None

    def live_stats(self) -> dict:
        """
        Current capital, profit-%, and rolling daily Sharpe.
        """
        profit_pct = (
            (self.capital - self.initial_capital) / self.initial_capital * 100
        )

        if self.data is not None and len(self.data) > 2:
            rets = self.data["price"].pct_change().dropna()
            sharpe = (
                (rets.mean() / rets.std() * np.sqrt(252)) if rets.std() else math.nan
            )
        else:
            sharpe = math.nan

        return {"capital": self.capital, "profit_pct": profit_pct, "sharpe": sharpe}
