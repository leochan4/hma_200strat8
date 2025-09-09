from ib_insync import *
import pandas as pd
import numpy as np


#HMA functions WMA and HMA

def WMA(series, period):
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda prices: np.dot(prices, weights) / weights.sum(), raw=True)

def HMA(series, period):
    half = int(period / 2)
    sqrt = int(np.sqrt(period))
    return WMA(2 * WMA(series, half) - WMA(series, period), sqrt)

#get candles and indicator data specifically for hma_200strat8

def get_hma_strat8_data(ib, contract):

    #gets candle bars

    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='10 D',
            barSizeSetting='15 mins',
            whatToShow='TRADES',
            useRTH=False,
            formatDate=1
        )

    #bars could not be retrieved

    except Exception as e:
        print(f"❌ Error fetching or processing data: {e}")
        return None, None
    
    #creates dataframe with bars and creates indicator values

    df = util.df(bars)
    df['HMA_200'] = HMA(df['close'], 200)
    df['SMA_300'] = df['close'].rolling(300).mean()
    df['SMA_25'] = df['close'].rolling(25).mean()
    df['HMA_diff'] = df['HMA_200'].diff()
    df['oc_pct_change'] = (df['close'] - df['open']) / df['open'] * 100

    #the most recent values

    latest = df.iloc[-1]

    #the values before the most recent values

    prev = df.iloc[-2] 

    return latest, prev