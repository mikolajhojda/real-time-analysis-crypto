
import websocket
import json
import pandas as pd
import threading
import time
from kafka import KafkaProducer

# Kafka Configuration
producer = KafkaProducer(
    bootstrap_servers='broker:9092',  # change to your Kafka broker
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)
KAFKA_TOPIC = 'binance-stream'

# Storage for 1-second bars
bars = []

def on_message(ws, message):
    global bars
    msg = json.loads(message)
    
    # Extract trade data
    price = float(msg['p'])       # trade price
    volume = float(msg['q'])      # trade quantity
    ts = int(msg['T']) // 1000    # timestamp in seconds

    # New 1s bucket or update existing
    if not bars or bars[-1]['bucket'] != ts:
        new_bar = {
            'bucket': ts,
            'open': price,
            'high': price,
            'low': price,
            'close': price,
            'volume': volume
        }
        bars.append(new_bar)
        producer.send(KAFKA_TOPIC, new_bar)  # Send new bar to Kafka
    else:
        bar = bars[-1]
        bar['high'] = max(bar['high'], price)
        bar['low'] = min(bar['low'], price)
        bar['close'] = price
        bar['volume'] += volume
        producer.send(KAFKA_TOPIC, bar)  # Update bar to Kafka

def on_error(ws, error):
    print(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed")

def run_ws():
    ws = websocket.WebSocketApp(
        "wss://stream.binance.com:9443/ws/btcusdt@trade",
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()

# Run WebSocket in background thread
t = threading.Thread(target=run_ws)
t.start()

try:
    while True:
        # Save bars locally every 5 minutes
        time.sleep(300)
        if bars:
            df = pd.DataFrame(bars)
            df['timestamp'] = pd.to_datetime(df['bucket'], unit='s')
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            df.to_csv('BTCUSDT_1s_ws.csv', index=False)
            print(f"Saved {len(df)} bars so far...")
except KeyboardInterrupt:
    print("Stopping and saving final data...")
    if bars:
        df = pd.DataFrame(bars)
        df['timestamp'] = pd.to_datetime(df['bucket'], unit='s')
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        df.to_csv('BTCUSDT_1s_ws.csv', index=False)
        print(f"Final save: {len(df)} bars.")
    t.join(timeout=1)
