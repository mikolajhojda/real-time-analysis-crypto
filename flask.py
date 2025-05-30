from flask import Flask, jsonify, request, Response
from kafka import KafkaConsumer
from RSI import MovingAverageRSIStrategy
import json, datetime, math, threading, collections, io
import matplotlib.pyplot as plt

BROKER = "broker:9092"
TOPIC = "binance-stream"
CACHE_BARS = 2_000
CACHE_DEC = 1_000
PLOT_LIMIT = 1200

app = Flask(__name__)

bars = collections.deque(maxlen=CACHE_BARS)
decisions = collections.deque(maxlen=CACHE_DEC)
stats = {"capital": None, "profit_pct": None, "sharpe": None}

strat = MovingAverageRSIStrategy(capital=10_000, short_period=12, long_period=26)


def _consumer_loop():
    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BROKER,
        auto_offset_reset="latest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )
    global stats
    for msg in consumer:
        bar = msg.value
        bars.append(bar)
        decision = strat.update(bar)
        if decision:
            decisions.append({"timestamp": bar["bucket"], "decision": decision, "price": bar["close"]})
        stats = strat.live_stats()


threading.Thread(target=_consumer_loop, daemon=True).start()


def _round(v, nd=2):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(v, nd)


def _ts(sec):
    return datetime.datetime.fromtimestamp(sec).isoformat()


def _decorate_bars(raw):
    return [{**b, "iso_ts": _ts(b["bucket"])} for b in raw]


def _profit_list():
    eq = strat.equity
    out = []
    for i in range(1, len(eq)):
        pct = (eq[i] - eq[i - 1]) / eq[i - 1] * 100
        out.append({"trade": i, "capital": _round(eq[i], 2), "profit_pct": _round(pct, 4)})
    return out


def _trades_list():
    trades = []
    tdec = list(decisions)
    n = 0
    i = 0
    while i < len(tdec) - 1:
        if tdec[i]["decision"] == "BUY" and tdec[i + 1]["decision"] == "SELL":
            n += 1
            buy, sell = tdec[i], tdec[i + 1]
            p_abs = sell["price"] - buy["price"]
            p_pct = p_abs / buy["price"] * 100
            trades.append({
                "trade": n,
                "buy_ts": buy["timestamp"],
                "buy_iso": _ts(buy["timestamp"]),
                "buy_price": _round(buy["price"], 2),
                "sell_ts": sell["timestamp"],
                "sell_iso": _ts(sell["timestamp"]),
                "sell_price": _round(sell["price"], 2),
                "profit_abs": _round(p_abs, 2),
                "profit_pct": _round(p_pct, 4),
            })
            i += 2
        else:
            i += 1
    return trades


def _trades_pretty(trades):
    if not trades:
        return "No closed trades yet."
    header = f"{'#':>3} | {'BUY ISO':19} | {'BUY':>11} | {'SELL ISO':19} | {'SELL':>11} | {'Δ':>9} | {'Δ%':>8}"
    lines = [header]
    for t in trades:
        lines.append(
            f"{t['trade']:>3} | {t['buy_iso']:<19} | {t['buy_price']:>11.2f} | "
            f"{t['sell_iso']:<19} | {t['sell_price']:>11.2f} | {t['profit_abs']:>9.2f} | {t['profit_pct']:>8.4f}"
        )
    return "\n".join(lines)


def _fig_to_png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _plot_price(limit=PLOT_LIMIT):
    data = list(bars)[-limit:]
    if not data:
        return None
    t = [datetime.datetime.fromtimestamp(b["bucket"]) for b in data]
    px = [b["close"] for b in data]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(t, px, label="close")
    for d in decisions:
        ts = datetime.datetime.fromtimestamp(d["timestamp"])
        if ts < t[0]:
            continue
        marker = "^" if d["decision"] == "BUY" else "v"
        color = "green" if d["decision"] == "BUY" else "red"
        ax.scatter(ts, d["price"], marker=marker, color=color, zorder=3)
    ax.set_title(f"BTCUSDT price (last {len(data)} bars)")
    ax.set_xlabel("time")
    ax.set_ylabel("price")
    fig.autofmt_xdate()
    return _fig_to_png(fig)


def _plot_profit():
    profs = _profit_list()
    if not profs:
        return None
    trades = [p["trade"] for p in profs]
    pct = [p["profit_pct"] for p in profs]
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.bar(trades, pct, width=0.8)
    ax.set_title("Profit % per trade")
    ax.set_xlabel("trade #")
    ax.set_ylabel("profit %")
    return _fig_to_png(fig)


@app.route("/")
def index():
    return jsonify({
        "/bars": "latest bars (limit param)",
        "/decisions": "recent BUY/SELL events",
        "/trades": "latest closed trades (limit param, json)",
        "/trades/plain": "pretty text table of trades (limit param)",
        "/stats": "current capital / P&L / Sharpe",
        "/equity": "equity curve array",
        "/profit": "per-trade realised profit %",
        "/plot/price": "static PNG price with decision markers",
        "/plot/profit": "static PNG profit chart",
        "/health": "heartbeat",
    })


@app.route("/bars")
def api_bars():
    limit = int(request.args.get("limit", 100))
    return jsonify(_decorate_bars(list(bars)[-limit:]))


@app.route("/decisions")
def api_decisions():
    limit = int(request.args.get("limit", 50))
    return jsonify(list(decisions)[-limit:])


@app.route("/trades")
def api_trades():
    limit = int(request.args.get("limit", 10))
    return jsonify(_trades_list()[-limit:])


@app.route("/trades/plain")
def api_trades_plain():
    limit = int(request.args.get("limit", 10))
    text = _trades_pretty(_trades_list()[-limit:])
    return Response(text, mimetype="text/plain")


@app.route("/stats")
def api_stats():
    return jsonify({"capital": _round(stats.get("capital")), "profit_pct": _round(stats.get("profit_pct")), "sharpe": _round(stats.get("sharpe"))})


@app.route("/equity")
def api_equity():
    return jsonify(strat.equity)


@app.route("/profit")
def api_profit():
    return jsonify(_profit_list())


@app.route("/health")
def api_health():
    return jsonify({"status": "ok", "bars_cached": len(bars)})


@app.route("/plot/price")
def plot_price_png():
    limit = int(request.args.get("limit", PLOT_LIMIT))
    img = _plot_price(limit)
    if img is None:
        return jsonify({"error": "no data yet"}), 400
    return Response(img, mimetype="image/png")


@app.route("/plot/profit")
def plot_profit_png():
    limit = int(request.args.get("limit", len(_profit_list())))
    img = _plot_profit()
    if img is None:
        return jsonify({"error": "no realised trades yet"}), 400
    return Response(img, mimetype="image/png")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
