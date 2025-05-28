# consumer_stream.py
"""
Stream bars from Kafka → 150-bar window strategy.
Print CSV lines and repeat the header every N rows so it never scrolls away.
"""

from kafka import KafkaConsumer
from RSI import MovingAverageRSIStrategy, WINDOW          # WINDOW = 150 in RSI.py
import json, datetime, math, sys

BROKER = "broker:9092"
TOPIC  = "binance-stream"
REPEAT_HEADER_EVERY = 25      # <─ print header after this many rows

# ── consumer -----------------------------------------------------------
consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers=BROKER,
    auto_offset_reset="latest",
    enable_auto_commit=True,
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
)

# ── strategy -----------------------------------------------------------
strat = MovingAverageRSIStrategy(capital=10_000, short_period=12, long_period=26)
bar_count = 0

HEADER = "ts,price,volume,decision,capital,profit_pct,sharpe"
print(HEADER)

for msg in consumer:
    bar = msg.value
    bar_count += 1

    # print the header periodically so it's always visible
    if bar_count % REPEAT_HEADER_EVERY == 0:
        print(HEADER)

    decision = strat.update(bar)                                     # still feed
    ts = datetime.datetime.fromtimestamp(bar["bucket"])
    '''
    if bar_count < WINDOW:
        print(f"{ts},{bar['close']:.2f},{bar['volume']:.6f},"
              f"too_little_data,NA,NA,NA")
        sys.stdout.flush()
        continue
    '''
    decision = decision or "NA"
    stats = strat.live_stats()
    sharpe_txt = (f"{stats['sharpe']:.2f}"
                  if not math.isnan(stats['sharpe']) else "NA")

    print(f"{ts},{bar['close']:.2f},{bar['volume']:.6f},"
          f"{decision},{stats['capital']:.2f},{stats['profit_pct']:.2f},{sharpe_txt}")
    sys.stdout.flush()

