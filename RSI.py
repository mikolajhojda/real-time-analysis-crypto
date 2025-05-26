import numpy as np
import matplotlib.pyplot as plt
import pandas as pd

from kafka import KafkaConsumer
import json
from datetime import datetime

class MovingAverageRSIStrategy:

    def __init__(self, capital, csv_file, short_period, long_period):
        self.data = None
        self.is_long = False
        self.short_period = short_period
        self.long_period = long_period
        self.capital = capital
        self.equity = [capital]
        self.csv_file = csv_file

    def load_data(self, from_kafka=False,
                      topic='binance-stream',
                      bootstrap_servers='broker:9092',
                      max_messages=1000):
            if from_kafka:
                consumer = KafkaConsumer(
                    topic,
                    bootstrap_servers=bootstrap_servers,
                    auto_offset_reset='earliest',
                    value_deserializer=lambda v: json.loads(v.decode('utf-8'))
                )
                records = []
                for i, msg in enumerate(consumer):
                    if i >= max_messages: 
                        break
                    price = msg.value             # assuming your producer sends a plain number
                    ts = datetime.fromtimestamp(msg.timestamp/1000)
                    records.append({'timestamp': ts, 'price': price})
                consumer.close()
                df = pd.DataFrame(records)
                df.set_index('timestamp', inplace=True)
            else:
                df = pd.read_csv(self.csv_file, parse_dates=['timestamp'])
                df.set_index('timestamp', inplace=True)
                df['price'] = df['close']
    
            self.data = df

    def construct_signals(self):
        self.data['short_ma'] = self.data['price'].ewm(span=self.short_period).mean()
        self.data['long_ma'] = self.data['price'].ewm(span=self.long_period).mean()
        self.data['move'] = self.data['price'] - self.data['price'].shift(1)
        self.data['up'] = np.where(self.data['move'] > 0, self.data['move'], 0)
        self.data['down'] = np.where(self.data['move'] < 0, self.data['move'], 0)
        self.data['average_gain'] = self.data['up'].rolling(14).mean()
        self.data['average_loss'] = self.data['down'].abs().rolling(14).mean()
        relative_strength = self.data['average_gain'] / self.data['average_loss']
        self.data['rsi'] = 100.0 - (100.0 / (1.0 + relative_strength))
        self.data = self.data.dropna()

    def plot_signals(self):
        plt.figure(figsize=(12, 6))
        plt.plot(self.data['price'], label='Price')
        plt.plot(self.data['short_ma'], label='Short MA', color='blue')
        plt.plot(self.data['long_ma'], label='Long MA', color='green')
        plt.title('Moving Average (MA) Crossover Trading Strategy with RSI')
        plt.xlabel('Date')
        plt.ylabel('Price')
        plt.legend()
        plt.show()

    def simulate(self):
        price_when_buy = 0

        for index, row in self.data.iterrows():
            if row['short_ma'] < row['long_ma'] and self.is_long:
                self.equity.append(row['price'] * self.capital / price_when_buy)
                self.is_long = False
            elif row['short_ma'] > row['long_ma'] and not self.is_long and row['rsi'] < 30:
                price_when_buy = row['price']
                self.is_long = True

    def plot_equity(self):
        plt.figure(figsize=(12, 6))
        plt.title('Equity Curve')
        plt.plot(self.equity, label='Equity', color='green')
        plt.xlabel('Trade Number')
        plt.ylabel('Capital ($)')
        plt.legend()
        plt.show()

    def show_stats(self):
        profit_pct = (self.equity[-1] - self.equity[0]) / self.equity[0] * 100
        returns = (self.data['price'] - self.data['price'].shift(1)) / self.data['price'].shift(1)
        sharpe = returns.mean() / returns.std() * np.sqrt(252)

        stats = pd.DataFrame([{
            "Profit (%)": profit_pct,
            "Final Capital": self.equity[-1],
            "Sharpe": sharpe
        }])
        # print as a neat table, two decimals
        print(stats.to_string(index=False, float_format="%.2f"))

if __name__ == '__main__':
    model = MovingAverageRSIStrategy(
        capital=100,
        csv_file='BTCUSDT_5s.csv',
        short_period=40,
        long_period=150
    )
    model.load_data(from_kafka=True, max_messages=2000)
    model.construct_signals()
    model.plot_signals()
    model.simulate()
    model.plot_equity()
    model.show_stats()