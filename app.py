# app.py  ── all-in-one live API & plots
# --------------------------------------
# 1.  Start your producer (websocket → Kafka 'binance-stream').
# 2.  pip install flask kafka-python matplotlib pillow
# 3.  python app.py
#
# Sample client:
#   curl http://127.0.0.1:5000/profit
#   curl http://127.0.0.1:5000/last5 | jq .
#   curl http://127.0.0.1:5000/profit_stream
#   curl -o profit.png http://127.0.0.1:5000/plot/profit
#
# In Python/Jupyter:
#   import requests, sseclient, io
#   from PIL import Image
#   png = requests.get("http://127.0.0.1:5000/plot/close").content
#   Image.open(io.BytesIO(png)).show()
#   resp = requests.get("http://127.0.0.1:5000/close_stream", stream=True)
#   for evt in sseclient.SSEClient(resp): print(evt.data)

import io, json, threading
from collections import deque
from datetime import datetime
from queue import Queue
from typing import List, Tuple

from flask import Flask, Response, jsonify, stream_with_context
from kafka import KafkaConsumer

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from RSI import MovingAverageRSIStrategy   # your existing class

# ─────────────── configuration ────────────────────────────────────────
BROKER  = "broker:9092"
TOPIC   = "binance-stream"
CAPITAL = 10_000
WINDOW  = 150                 # points kept for plots & strategy window

# ─────────────── global state / buffers ───────────────────────────────
bars_buf   : deque[dict]                 = deque(maxlen=5)
close_buf  : deque[Tuple[datetime, float]] = deque(maxlen=WINDOW)
profit_buf : deque[Tuple[datetime, float]] = deque(maxlen=WINDOW)

profit_val = {"profit_pct": None}

profit_q   = Queue()          # push new profit for SSE
close_q    = Queue()          # push new close  for SSE

# instantiate the trading strategy
strategy = MovingAverageRSIStrategy(
    capital=CAPITAL, short_period=12, long_period=26
)

# ─────────────── Kafka consumer thread ────────────────────────────────
def kafka_worker():
    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=BROKER,
        auto_offset_reset="latest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )
    last_profit = None
    for msg in consumer:
        bar = msg.value
        ts  = datetime.fromtimestamp(bar["bucket"])

        # buffers
        bars_buf.append(bar)
        close_buf.append((ts, bar["close"]))

        # strategy / profit update
        strategy.update(bar)
        stats = strategy.live_stats()
        pct   = round(stats["profit_pct"], 4)
        profit_buf.append((ts, pct))

        # broadcast changes
        if pct != last_profit:
            profit_val["profit_pct"] = pct
            profit_q.put(pct)
            last_profit = pct
        close_q.put(bar["close"])

threading.Thread(target=kafka_worker, daemon=True).start()

# ─────────────── flask helpers ────────────────────────────────────────
def _plot_png(series: List[Tuple[datetime, float]], title: str, ylabel: str) -> bytes:
    fig, ax = plt.subplots(figsize=(8, 3))
    if series:
        xs, ys = zip(*series)
        ax.plot(xs, ys, linewidth=1)
        fig.autofmt_xdate()
    else:
        ax.text(0.5, 0.5, "No data yet", ha="center", va="center")
        ax.axis("off")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()

# ─────────────── Flask app ────────────────────────────────────────────
app = Flask(__name__)

@app.route("/profit")
def profit():
    return jsonify(profit_val)

@app.route("/last5")
def last5():
    return jsonify(list(bars_buf))

# Server-Sent Events streams
def _sse(queue: Queue):
    @stream_with_context
    def gen():
        # push current value immediately if known
        try:
            latest = queue.queue[-1]        # type: ignore
            yield f"data: {latest}\n\n"
        except IndexError:
            pass
        while True:
            val = queue.get()
            yield f"data: {val}\n\n"
    return Response(gen(), mimetype="text/event-stream")

@app.route("/profit_stream")
def profit_stream():
    return _sse(profit_q)

@app.route("/close_stream")
def close_stream():
    return _sse(close_q)

# PNG plots
@app.route("/plot/profit")
def plot_profit():
    return Response(_plot_png(list(profit_buf), "Realised Profit %", "%"),
                    mimetype="image/png")

@app.route("/plot/close")
def plot_close():
    return Response(_plot_png(list(close_buf), "Close Price", "USDT"),
                    mimetype="image/png")

# ─────────────── main ────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

