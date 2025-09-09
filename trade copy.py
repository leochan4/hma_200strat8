from ib_insync import LimitOrder
import datetime
import time


class Trade:
    slippage = 0.001           # initial slippage
    adaptive_inc = 0.0005      # slippage increase per retry

    def __init__(self, ib, contract, signal, size, adaptive_slippage=True):
        self.ib = ib
        self.contract = contract
        self.signal = signal.upper()
        self.size = size
        self.adaptive_slippage = adaptive_slippage
        self.trade = None
        self.fill_time = None
        self.start_time = datetime.datetime.now()
        self.retry_count = 0
        self.final_slippage = self.slippage
        self.TEST_MODE = False

    def _calculate_limit_price(self, price):
        if self.signal == 'BUY':
            return round(price * (1 + self.slippage), 2)
        elif self.signal == 'SELL':
            return round(price * (1 - self.slippage), 2)
        else:
            raise ValueError("Direction must be 'BUY' or 'SELL'")

    def _place_limit_order(self, price):
        limit_price = self._calculate_limit_price(price)
        order = LimitOrder(self.signal, self.size, limit_price, outsideRth=True)
        self.trade = self.ib.placeOrder(self.contract, order)
        self.ib.sleep(1)  # allow IBKR to update order status

        status = self.trade.orderStatus.status
        if status in ['Inactive', 'Rejected']:
            print(f"❌ Order was {status} immediately after submission.")
            return None
        return limit_price

    def fill_and_ensure(self, max_wait_min=15, retry_interval_sec=60):
        if self.TEST_MODE:
            mock_price = self._get_current_price()
            print(f"[TEST_MODE] Simulated {self.signal} of {self.size} at {mock_price}")
            return True, mock_price

        timeout = self.start_time + datetime.timedelta(minutes=max_wait_min)
        retry_count = 0

        while datetime.datetime.now() < timeout:
            current_price = self._get_current_price()
            limit_price = self._place_limit_order(current_price)
            if limit_price is None:
                return False, None

            print(f"Placed {self.signal} order at {limit_price} - waiting for fill...")
            filled = self._wait_for_fill(timeout=retry_interval_sec)

            if filled:
                actual_fill_price = self.trade.fills[-1].price if self.trade.fills else limit_price
                print(f"✅ Order filled at {self.fill_time} for {actual_fill_price}")
                self.retry_count = retry_count
                self.final_slippage = self.slippage
                return True, actual_fill_price

            if self.adaptive_slippage:
                self.slippage += self.adaptive_inc
                print(f"⏫ Slippage increased to {self.slippage:.4f}")

            retry_count += 1
            print(f"⚠️ Not filled in {retry_interval_sec}s - cancelling and retrying (attempt #{retry_count})")
            self.ib.cancelOrder(self.trade.order)
            self.ib.sleep(2)

        print(f"❌ Order not filled within {max_wait_min} minutes.")
        return False, None

    def _wait_for_fill(self, timeout):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            self.ib.sleep(1)
            if self.trade.orderStatus.status == 'Filled':
                if self.trade.fills:
                    self.fill_time = self.trade.fills[-1].time
                return True

        # Last-minute double-check
        if self.trade.orderStatus.status == 'Filled' and self.trade.fills:
            self.fill_time = self.trade.fills[-1].time
            return True
        return False

    def _get_current_price(self):
        ticker = self.ib.reqMktData(self.contract, snapshot=True, regulatorySnapshot=False)
        self.ib.sleep(2)

        price = ticker.last or ticker.close or ticker.bid or ticker.ask
        if not price:
            raise ValueError("❌ No valid price available from market data.")
        return price