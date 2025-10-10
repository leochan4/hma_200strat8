from ib_insync import *
import pandas as pd
import numpy as np
import math

def _get_netliquidation(ib, currency_preference=("USD", "CAD"), tries=5, sleep_sec=0.5):
    for _ in range(tries):
        summary = ib.accountSummary()
        df = util.df(summary)
        if not df.empty:
            for cur in currency_preference:
                nl = df[(df.tag == 'NetLiquidation') & (df.currency == cur)]
                if not nl.empty:
                    return float(nl['value'].astype(float).iloc[0])

        ib.sleep(sleep_sec)

    if not df.empty:
        nl_any = df[df.tag == 'NetLiquidation']
        if not nl_any.empty:
            return float(nl_any['value'].astype(float).iloc[0])
    raise RuntimeError("NetLiquidation (equity) not available from accountSummary()")      


def calc_pos_size(ib, price, KELLY_f = 0.25, min_size=1):

    # get NetLiquidation (your total account equity)
    equity = _get_netliquidation(ib)

    print(f"Current equity: {equity}")

    pos_size = max(0.0, equity * KELLY_f)

    size = max(min_size, int(pos_size / max(price, 1e-9)))
    return size