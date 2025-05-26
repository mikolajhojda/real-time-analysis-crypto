import requests
from kafka import KafkaProducer
from time import sleep
import json

producer = KafkaProducer(
    bootstrap_servers='broker:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

def get_crypto_price(crypto):
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto}&vs_currencies=usd"
    response = requests.get(url)
    data = response.json()
    return data.get(crypto, {}).get('usd')

# Endless loop instead of just one iteration
while True:
    price = get_crypto_price('bitcoin')
    print(price)
    if price is not None:
        producer.send('binance-stream', value=price)
        producer.flush()      # make sure it actually goes out
    sleep(10)

# run with: python producer_spark.py