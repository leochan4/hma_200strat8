#CHATGPT VALIDATED#


from ib_insync import LimitOrder
import datetime
import time

from position_size_calc import calc_pos_size

class Trade:
    slippage = 0.001           # initial slippage
    adaptive_inc = 0.0005      # slippage increase per retry

    def __init__(self, ib, contract, signal, adaptive_slippage=True):
        self.ib = ib
        self.contract = contract
        self.signal = signal.upper()
        self.adaptive_slippage = adaptive_slippage
        self.trade = None
        self.fill_time = None
        self.start_time = datetime.datetime.now()
        self.retry_count = 0
        self.final_slippage = self.slippage
        self.size = 0
        self.avg_fill_price  = None
        self.filled_qty = 0
        self.total_comm = 0.0
        self.order_ids = []
        self.TEST_MODE = False


    def _get_size(self, price):
        return calc_pos_size(self.ib, price)
        
    def _get_current_price(self, timeout = 5):
        ticker = self.ib.reqMktData(self.contract, snapshot=True, regulatorySnapshot=False)
        self.ib.waitOnUpdate(timeout)

        price = ticker.last or ticker.close or ticker.bid or ticker.ask
        if not price:
            raise ValueError("No valid price available from market data.")
        return price
    

    
    def _calculate_limit_price(self, price):
        if self.signal == 'BUY':
            return round(price * (1 + self.slippage), 2)
        elif self.signal == 'SELL':
            return round(price * (1 - self.slippage), 2)
        else:
            raise ValueError("Direction must be 'BUY' or 'SELL'")
    


    def fill_and_ensure(self, max_wait_min=15, retry_interval_sec=60):
        if self.TEST_MODE:
            mock_price = self._get_current_price()

            if self.size <= 0: #computes the position size if it is test mode and the _place_limit_order() function isn't called
                self.size = self._get_size(mock_price)
                self.avg_fill_price = mock_price
                self.filled_qty = self.size

            print(f"[TEST_MODE] Simulated {self.signal} of {self.size} at {mock_price}")
            return True
        
        deadline = self.start_time + datetime.timedelta(minutes=max_wait_min)
        retry_count = 0
        filled_qty_total = 0
        #vwap in this case is the average fill price at each partial fill weighted by volume at each partial fill
        vwap_numer = 0.0

        
        px0 = self._get_current_price()
        target_size = self._get_size(px0)
        self.size = target_size

        seen_exec_ids = set()

        
        while datetime.datetime.now() < deadline and filled_qty_total < target_size:

            px = self._get_current_price()

            remaining = target_size - filled_qty_total
            #in the case that target size is filled
            if remaining <= 0:
                break
            
            limit_price = self._calculate_limit_price(px)
            order = LimitOrder(self.signal, remaining, limit_price, outsideRth=True, tif='DAY')
            self.trade = self.ib.placeOrder(self.contract, order)
            self.order_ids.append(self.trade.order.orderId)
            self.ib.waitOnUpdate(1)

            st = self.trade.orderStatus.status
            if st in ('Inactive', 'Rejected'):
                print(f"Order was {st} immediately after submission")

                self.filled_qty = int(filled_qty_total)
                self.avg_fill_price = (vwap_numer / filled_qty_total) if filled_qty_total else None
                # optional quick commission sweep:
                self.total_comm = sum(
                    float(fr.commissionReport.commission)
                    for fr in (getattr(self.trade, "fills", []) or [])
                    if getattr(fr, "commissionReport", None) and fr.commissionReport.commission is not None
                )

                return False
            
            print(f"Placed {self.signal} {remaining} @ {limit_price} — waiting for fill...")

            start = time.monotonic()

            while time.monotonic() - start < retry_interval_sec:
                self.ib.waitOnUpdate(1)

                if getattr(self.trade, "fills", None):
                    for f in self.trade.fills:
                        ex_id = getattr(f.execution, "execId", None)
                        #does not add duplicate ids into sum
                        if ex_id and ex_id in seen_exec_ids:
                            continue
                        if ex_id:
                            seen_exec_ids.add(ex_id)
                        
                        sh = int(f.execution.shares)
                        pr = float(f.execution.price)

                        if sh > 0:
                            vwap_numer += pr * sh
                            filled_qty_total += sh

                        if getattr(f, "commissionReport", None) and f.commissionReport.commission is not None:
                            self.total_comm += float(f.commissionReport.commission)

                if filled_qty_total >= target_size or self.trade.orderStatus.status == 'Filled':
                    break

                self.ib.sleep(0.25)



            if filled_qty_total >= target_size:
                break


            if self.trade.orderStatus.status not in ('Cancelled', 'ApiCancelled', 'Filled'):
                self.ib.cancelOrder(self.trade.order)
                
                #repeatedly checks for cancel complete
                for _ in range(20):
                    self.ib.waitOnUpdate(0.5)
                    if self.trade.orderStatus.status in ('Cancelled', 'ApiCancelled', 'Filled'):
                        break

            #post cancel sweep for late fills
            self.ib.sleep(0.25)

            if getattr(self.trade, "fills", None):
                for f in self.trade.fills:
                    ex_id = getattr(f.execution, "execId", None)
                    if ex_id and ex_id in seen_exec_ids:
                        continue
                    if ex_id:
                        seen_exec_ids.add(ex_id)

                    sh = int(f.execution.shares)
                    pr = float(f.execution.price)
                    if sh > 0:
                        vwap_numer += pr * sh
                        filled_qty_total += sh

                    if getattr(f, "commissionReport", None) and f.commissionReport.commission is not None:
                        self.total_comm += float(f.commissionReport.commission)

            if filled_qty_total >= target_size:
                break

            if self.adaptive_slippage:
                self.slippage = min(self.slippage + self.adaptive_inc, 0.004)
                print(f"Slippage increased to {self.slippage:.4f}")
            retry_count += 1
                

        if filled_qty_total >= target_size:

            avg_fill = vwap_numer / filled_qty_total if filled_qty_total else None

            self.fill_time = (self.trade.fills[-1].time if getattr(self.trade, "fills", None) else None)
            self.retry_count = retry_count
            self.final_slippage = self.slippage

            self.avg_fill_price = avg_fill
            self.filled_qty = int(filled_qty_total)
                            
            
            print(f"✅ Order filled at {self.fill_time} for {avg_fill} (qty={filled_qty_total})")
            return True
    
        print(f"❌ Order not fully filled within {max_wait_min} minutes. Filled {filled_qty_total}/{target_size}.")
        return False
    