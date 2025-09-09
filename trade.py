from ib_insync import *
import datetime
import time


#every trade is an object

class Trade:

    #slippage set into limit order price

    slippage = 0.001

    #incremental increase in slippage if order entry fails

    adaptive_inc=0.0005

    #change adaptive_slippage to 'False' if not required

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
        self.TEST_MODE = True


    #calculates limit price using the slippage var
    def _calculate_limit_price(self, price):
        if self.signal == 'BUY':
            return round(price * (1+self.slippage), 2)
        elif self.signal == 'SELL':
            return round(price * (1-self.slippage), 2)
        else:
            raise ValueError("Direction must be 'BUY' or 'SELL'")

    #places the limit order and returns the filled limit order price
        
    def _place_limit_order(self, price):
        # Calculate adjusted limit price
        limit_price = self._calculate_limit_price(price)
    
        # Create limit order object
        order = LimitOrder(self.signal, self.size, limit_price, outsideRth=True)
    
        # Place order through IB
        self.trade = self.ib.placeOrder(self.contract, order)
    
        # Sleep briefly to allow IBKR to process order status
        self.ib.sleep(1)
    
        # Check for immediate rejection or inactive order
        status = self.trade.orderStatus.status
        if status in ['Inactive', 'Rejected']:
            print(f" Order was {status} immediately after submission.")
            return None  # signal failure to caller

        return limit_price
    
    
    #ensures order is filled by retrying if the previous attempt fails

        #does this within one candle length (15min) and gives 60 sec to fill each order

    def fill_and_ensure(self, max_wait_min=15, retry_interval_sec=60):


        if self.TEST_MODE:
            mock_price = self._get_current_price()
            print(f"[TEST_MODE] Simulated {self.signal} of {self.size} shares at {mock_price}")
            return True, mock_price

        #gives the time when script stops retrying

        timeout = self.start_time + datetime.timedelta(minutes=max_wait_min)

        #counter for retrying limit order entry

        retry_count = 0

        #gets current price of the ticker, and calculates limit price
        while datetime.datetime.now() < timeout:
            current_price = self._get_current_price()
            #This is where the order is placed
            limit_price = self._place_limit_order(current_price)

            if limit_price is None:
                return False, None

            print(f"Placed {self.signal} order at {limit_price} - waiting for fill...")

            #waits 60 sec for the order fill

            filled = self._wait_for_fill(timeout=retry_interval_sec)

            if filled:

                #prints the price at which the order fills, returns that price
                actual_fill_price = self.trade.fills[-1].price if self.trade.fills else limit_price
                print(f"Order filled at {self.fill_time} for {actual_fill_price}")
                self.retry_count = retry_count
                self.final_slippage = self.slippage

                return True, actual_fill_price
            
            #if order does not fill, increase the slippage
            if self.adaptive_slippage:
                self.slippage += self.adaptive_inc
                print(f"Slippage increased to {self.slippage:.4f}")

            retry_count += 1

            #cancels the current order, and retries in next loop with the increased slippage

            print(f"Not filled in {retry_interval_sec}s - cancelling and starting retry #{retry_count}")
            self.ib.cancelOrder(self.trade.order)

            self.ib.sleep(2)  # Give IBKR a moment before retrying
            
        print(f"Order not filled within the {max_wait_min}min window.")
        return False, None

    #waits for order fill for 'timeout' amount of seconds
    def _wait_for_fill(self, timeout):
        
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            self.ib.sleep(1)
            if self.trade.orderStatus.status == 'Filled':
                if self.trade.fills:
                    self.fill_time = self.trade.fills[-1].time
                return True
            
        if self.trade.orderStatus.status == 'Filled' and self.trade.fills:
            self.fill_time = self.trade.fills[-1].time
            return True
        
        return False
    
    def _get_current_price(self):
        bars = self.ib.reqHistoricalData(
            self.contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='1 min',
            whatToShow='TRADES',
            useRTH=False,
            formatDate=1,
            keepUpToDate=False  # Ensure it’s just snapshot historical
        )
        df = util.df(bars)
        if df.empty:
            raise ValueError("❌ No historical data returned.")
        return df['close'].iloc[-1]  # use latest close
    


    '''def _get_current_price(self):

        #retrieves the most recent trading price of ticker

        ticker = self.ib.reqMktData(self.contract, snapshot=True, regulatorySnapshot=False)
        self.ib.sleep(2)

        price = ticker.last or ticker.close or ticker.bid or ticker.ask

        if not price:
            raise ValueError("No valid price available from market data.")
        return price'''
    
    