# Real Time Analysis of Crypto Data

A real-time data analysis pipeline that consumes streaming financial data. It integrates Apache Kafka for publishing and consuming data, calculates trading strategy and uses Flask via HTTP endpoints.

## Structure
```
rta/
├── src/
│   ├── producer.py        # Streams data to Kafka
│   ├── consumer.py        # Listens to Kafka and processes data
│   ├── RSI.py             # Computes RSI from price data
│   ├── flask.py           # Serves analytics via API
│   ├── app_use.ipynb      # Example usage
└── README.md
```

## Installation
```
git clone https://github.com/mikolajhojda/rta.git
cd rta
```

## Usage
### 1. Create Kafka topic
```
cd ~
ls -la
```

```
kafka/bin/kafka-topics.sh --bootstrap-server broker:9092 --create --topic binance-stream
```

### 2. Start the Producer
```
python producer.py
```

### 3. Start the Consumer
```
python consumer.py
```

### 4. Launch the Flask API
```
python flask.py
```
