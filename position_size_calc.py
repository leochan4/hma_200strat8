from ib_insync import *
import pandas as pd
import numpy as np
import math


KELLY_f = 0.25

def calc_pos_size(ib, price, account: str = None):

    if price <= 0:
        raise ValueError("Price must be > 0 to calculate position size.")
    

    summary_df = util.df(ib.accountSummary(account))
    nl = summary_df[summary_df['tag'] == 'NetLiquidation']

    if nl.empty:
        raise RuntimeError("NetLiquidation not found in account summary")

    # get NetLiquidation (your total account equity)
    equity = float(nl.loc[0]['value'])
    currency = nl.loc[0]['currency']

    print(f"Current equity: {equity} {currency}") 

    pos_size = equity * KELLY_f

    stock_units = math.floor(pos_size/price)


    return stock_units