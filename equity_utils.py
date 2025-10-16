# equity_utils.py
# Reusable helpers to connect, fetch NetLiquidation (equity),
# get a robust reference price, and compute position size.
# Requires: pip install ib-insync python-dotenv

from __future__ import annotations
import os, time, math
from typing import Tuple
from ib_insync import IB, util, Stock

DEFAULT_HOST = os.getenv("IB_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("IB_PORT", "7497"))        # 7497=paper, 7496=live
DEFAULT_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", "1001"))

def connect_or_retry(ib: IB,
                     host: str = DEFAULT_HOST,
                     port: int = DEFAULT_PORT,
                     client_id: int = DEFAULT_CLIENT_ID,
                     tries: int = 5) -> int:
    """Connect to IB with retries; auto-bump clientId if 'already in use'."""
    if ib.isConnected():
        return ib.client.clientId
    last_exc = None
    cid = client_id
    for n in range(tries):
        try:
            ib.connect(host, port, clientId=cid, timeout=10)
            ib.reqMarketDataType(1)  # 1=live, 3=delayed
            return cid
        except Exception as e:
            last_exc = e
            ib.disconnect()
            if "client id is already in use" in str(e).lower():
                cid += 1
            time.sleep(1 + n * 0.5)
    raise RuntimeError(f"Unable to connect to IB after retries: {last_exc}")

def get_net_liquidation(ib: IB,
                        tries: int = 5,
                        sleep_sec: float = 0.5,
                        prefer_currencies=("USD","CAD")) -> float:
    """Return NetLiquidation as float, retrying right after connect."""
    last_df = None
    for _ in range(tries):
        df = util.df(ib.accountSummary())
        last_df = df
        if not df.empty:
            for cur in prefer_currencies:
                nl = df[(df.tag == 'NetLiquidation') & (df.currency == cur)]
                if not nl.empty:
                    val = float(nl['value'].astype(float).iloc[0])
                    if math.isfinite(val):
                        return val
            # fallback: any currency
            nl_any = df[df.tag == 'NetLiquidation']
            if not nl_any.empty:
                val = float(nl_any['value'].astype(float).iloc[0])
                if math.isfinite(val):
                    return val
        ib.sleep(sleep_sec)
    raise RuntimeError("NetLiquidation not available/finite (accountSummary not ready).")

def get_ref_price(ib: IB, contract: Stock, attempts: int = 3, timeout: float = 5.0) -> float:
    """Grab a robust reference price using multiple fields (last/close/marketPrice/bid/ask)."""
    for _ in range(attempts):
        t = ib.reqMktData(contract, snapshot=True, regulatorySnapshot=False)
        ib.waitOnUpdate(timeout)
        price = t.last or t.close or t.marketPrice() or t.bid or t.ask
        if price is not None and math.isfinite(price) and price > 0:
            return float(price)
    raise RuntimeError("No valid price from market data (last/close/bid/ask all missing).")

def calc_pos_size(ib: IB, ref_price: float, risk_frac: float = 0.01, min_size: int = 1) -> Tuple[int, float, float]:
    """Compute integer position size given equity*risk_frac and a reference price.
       Returns (size, equity, dollars_risked)."""
    if ref_price is None or not math.isfinite(ref_price) or ref_price <= 0:
        raise ValueError(f"Invalid reference price: {ref_price}")
    equity = get_net_liquidation(ib)
    dollars = max(0.0, float(equity) * float(risk_frac))
    size = max(int(min_size), int(dollars / ref_price))
    return size, float(equity), dollars