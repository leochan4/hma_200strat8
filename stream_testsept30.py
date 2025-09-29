import sys
import time
from datetime import datetime
from ib_insync import *

HOST = '127.0.0.1'
PORT = 7497
CLIENT_ID = 42

SYMBOL = sys.argv[1].upper() if len(sys.argv) > 1 else 'AAPL'

def md_type_str(code: int) -> str:
    return {
        1: "REALTIME",
        2: "FROZEN",
        3: "DELAYED",
        4: "DELAYED_FROZEN"
    }.get(code, f"UNKNOWN({code})")

def main():
    ib = IB()

    def on_error(reqId, errorCode, errorString, contract):
        print(f"\n[IB ERROR] {errorCode}: {errorString}")

    ib.errorEvent += on_error

    print(f"connecting to TWS/Gateway at {HOST}:{PORT} (clientId={CLIENT_ID}) ...")
    ib.connect(HOST, PORT, clientId=CLIENT_ID)

    #requests market data liva data if permitted (1 = realtime data, 3 = delayed data)

    ib.reqMarketDataType(1)

    contract = Stock(SYMBOL, 'SMART', 'USD', primaryExchange='NASDAQ')
    ticker = ib.reqMktData(contract, '', False, False)

    print(f"Subscribing to {SYMBOL}")
    ok = ib.waitOnUpdate(timeout=5)
    if not ok:
        print("No initial data received within 5s")
        ib.disconnect()
        return
    
    md_code = getattr(ticker, 'marketDataType', None)
    print(f"MarketDataType reported: {md_type_str(md_code)}")

    try:
        ib.reqTickByTickData(contract, tickType='Last', numberOfTicks=0, ignoreSize=False)
    except Exception as e:
        print(f"TickByTick not available: {e}")

    print("\nStreaming (ctrl + c) to stop)...")
    print(" Time (local)     | Type     | Bid        Ask        Last       Vol    Exch ")
    print("------------------+----------+----------------------------------------------")

    try:
        last_print = 0.0

        while True:
            ib.waitOnUpdate(timeout=1.0)
            
            bid = ticker.bid
            ask = ticker.ask
            last = ticker.last
            bsz = ticker.bidSize
            asz = ticker.askSize
            lsz = ticker.lastSize
            vol = ticker.volume
            exch = ticker.lastExchange or ''
            md_code = getattr(ticker, 'marketDataType', md_code)

            now = time.time()
            if now - last_print >= 1.0:
                ts = datetime.now().strftime("%H:%M:%S")
                type_label = md_type_str(md_code)
                print(f" {ts} | {type_label:<8} | "
                      f"{(bid if bid is not None else float('nan')):>7.2f} x"
                      f"{(bsz if bsz is not None else 0):<4}  "
                      f"{(ask if ask is not None else float('nan')):>7.2f} x"
                      f"{(asz if asz is not None else 0):<4}  "
                      f"{(last if last is not None else float('nan')):>7.2f}  "
                      f"{(vol if vol is not None else 0):>8}  {exch}")
                last_print = now

    except KeyboardInterrupt:
        print("\nStopping stream")

    finally:
        try:
            ib.cancelTickByTickData(contract, 'Last')
            
        except Exception:
            pass
        ib.cancelMktData(contract)
        ib.disconnect()
        print("disconnected")


if __name__ == "__main__":
    main()
    