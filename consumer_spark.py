# filepath: /Users/mikolajrostkowski/Desktop/PROGRAMOWANIE/python-code/UCZELNIA/RTA/spark_rsi.py
from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from pyspark.sql.types import DoubleType
from RSI import MovingAverageRSIStrategy
import pandas as pd

spark = SparkSession.builder \
    .appName("KafkaRSIStrategy") \
    .getOrCreate()

kafka_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "broker:9092") \
    .option("subscribe", "binance-stream") \
    .option("startingOffsets", "earliest") \
    .load()

price_df = kafka_df \
    .selectExpr("timestamp", "CAST(value AS STRING) AS price_str") \
    .withColumn("price", col("price_str").cast(DoubleType())) \
    .select("timestamp", "price")

strat = MovingAverageRSIStrategy(100, None, 40, 150)

def process_batch(df, epoch_id):
    pdf = df.toPandas()
    if pdf.empty: 
        return

    # append new rows to historic buffer
    pdf.set_index("timestamp", inplace=True)
    if strat.data is None:
        strat.data = pdf
    else:
        strat.data = pd.concat([strat.data, pdf]).sort_index()

    # a growing DataFrame—compute signals on the full history
    strat.construct_signals()
    strat.simulate()

    print(f"\n=== Batch {epoch_id} (history_size={len(strat.data)}) ===")
    strat.show_stats()
    print("="*30)
    
query = price_df.writeStream \
    .foreachBatch(process_batch) \
    .outputMode("append") \
    .start()

query.awaitTermination()

# run with:
# spark-submit \
#   --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.0 \
#   consumer_spark.py