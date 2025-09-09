from ib_insync import LimitOrder

def limit_order(ib, slippage_pct, signal, contract, position_size, price):

    if signal == 'BUY':
        limit_price = round(price * (1 + slippage_pct), 2)
    elif signal == 'SELL':
        limit_price = round(price * (1 - slippage_pct), 2)
    else:
        raise ValueError("Signal must be 'BUY' or 'SELL'")
    
    order = LimitOrder(signal, position_size, limit_price, outsideRth=True)
    trade = ib.placeOrder(contract, order)

    return trade