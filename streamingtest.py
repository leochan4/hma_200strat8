from ib_insync import *

# Connect to TWS or IB Gateway (make sure it's running!)
ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)  # 7497 = TWS paper/live, 4002 = Gateway

# Define the contract (NASDAQ AAPL as example)
contract = Stock('AAPL', 'SMART', 'USD')

# Request streaming market data
ticker = ib.reqMktData(contract, snapshot=False)

print("✅ Subscribed to live data for AAPL")
print("Waiting for first tick...")

# Wait until IBKR sends at least one tick
ib.sleep(2)

# Print out the first available values
print(f"Last: {ticker.last}, Bid: {ticker.bid}, Ask: {ticker.ask}")

# Keep printing updates as they come in
def onPendingTicker(t):
    print(f"Update -> Last: {t.last}  Bid: {t.bid}  Ask: {t.ask}")

ib.pendingTickersEvent += onPendingTicker

ib.run()  # keeps loop alive to receive live ticks