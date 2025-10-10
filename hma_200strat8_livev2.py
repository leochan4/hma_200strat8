##############################################################################
#TO DO
#DONE #Stay in TESTMODE while I don't have live price streaming. Test code logic first. 
#change reqHistoricalData() to reqMktData() once ready to get live price streaming.

#DONE line 211#    change IBKR password to remove capital letters
#watchdog.py does not work
#check to see if current subscription does give instantaneous price, or if there has to be a delay. 

#Create a trade exit during high-volatility times like earnings and FOMC rate decisions


#in the big loop, if an exception error is thrown, have it disconnect. Next loop, it will try reconnecting again, but have the reconnected be limited to 5 attempts. 
###############################################################################

#verfied#

from ib_insync import *
import sys 
import pandas as pd
import numpy as np
import time
import datetime
import os
import traceback
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
import json
import pandas_market_calendars as mcal
from zoneinfo import ZoneInfo

# local market timezone, not local computer's
NY = ZoneInfo("America/New_York")

COMM_PER_SHARE = 0.01

BASE_CLIENT_ID = 1001



from tradev2 import Trade
from get_data import get_hma_strat8_data
from state_functions import load_state, write_state

# paused status will change to 'true' if an exit order is not filled
# the algo will unpause if a pause sentinel is created in the folder. This file will be removed once continues

PAUSE_SENTINEL = "resume.txt" 

#loads email information

load_dotenv()

#global position size, and slippace percentage

#position_size = 10
ticker = 'NVDA'

#sets the email info from env. into these

email_settings = {
    'sender': os.getenv('EMAIL_SENDER'),
    'recipient': os.getenv('EMAIL_RECIPIENT'),
    'smtp_server': os.getenv('SMTP_SERVER'),
    'smtp_port': int(os.getenv('SMTP_PORT')),
    'username': os.getenv('EMAIL_SENDER'),
    'password': os.getenv('EMAIL_PASSWORD')
}

# === Returns the current time in whole 15mins === #

def floor_to_bar(dt, minutes=15):
    m = (dt.minute // minutes) * minutes
    return dt.replace(minute=m, second=0, microsecond=0)

# === CSV Logger ===

def log_trade(entry_time, action, entry_type, entry_price, exit_price, fill_qty, comm, filename='trade_log.csv'):

    #calculates PnL on completed trade
    if action == "SHORT":
        pnl = (entry_price - exit_price)*fill_qty
    elif action == "LONG":
        pnl = (exit_price - entry_price)*fill_qty
    else:
        pnl = None

    #pnl = round((exit_price - entry_price)*-1, 4) if action == 'SHORT' else round(entry_price - exit_price, 4)
    
    #columns of logged data
    record = {
        'Time': entry_time,
        'Action': action,
        'Entry Type': entry_type,
        'Entry Price': round(entry_price, 2),
        'Exit Price': round(exit_price, 2),
        'Fill Quantity': fill_qty,
        'Commissions': comm,
        'PnL': round(pnl, 2) if pnl is not None else None
    }

    #convert to df
    df = pd.DataFrame([record])

    #exports to .csv
    df.to_csv(filename, mode='a', index=False, header=not os.path.exists(filename))


# === Email Alert ===

def send_email(subject, body, config):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = config['sender']
    msg['To'] = config['recipient']

    #connects to SMPT server
    try:
        with smtplib.SMTP_SSL(config['smtp_server'], config['smtp_port']) as server:
            server.login(config['username'], config['password'])
            server.send_message(msg)
    except Exception as e:
        print(f"Email failed: {e}")


# === Get local Time Zone === #

def now_tz(tz: str = "NY") -> datetime.datetime:
    if tz == "NY":
        return datetime.datetime.now(NY)
    if tz == "LOCAL":
        return datetime.datetime.now().astimezone()
    raise ValueError("tz must be 'NY' or 'LOCAL'")

# === Exception Log ===

def log_exception(message, filename='error_log.txt', tz = 'NY'):
    dt = now_tz(tz)
    with open(filename, 'a', encoding='utf-8') as f:
        f.write(f"{dt:%Y-%m-%d %H:%M:%S %Z}: {message}\n")


# === Backup Log File === #

def backup_file(src_path, backup_dir='backups', tz = 'NY'):
    import shutil, os
    os.makedirs(backup_dir, exist_ok=True)
    ts = now_tz(tz).strftime('%Y%m%d_%H%M%S')

    #creates new backup path
    backup_path = os.path.join(backup_dir, f"{os.path.basename(src_path).split('.')[0]}_{ts}.csv")
    if os.path.exists(src_path):
        shutil.copy(src_path, backup_path)


# === Checks if market it open === #

def is_market_open_extended():
    """
    Check if current time is within premarket, regular, or postmarket trading hours (Eastern Time).
    Returns True if within any trading window.
    """

    '''# Current time in US/Eastern timezone
    from pytz import timezone
    eastern = timezone('US/Eastern')
    now = datetime.datetime.now(eastern).time()

    # Extended trading hours for NASDAQ/NYSE (Eastern Time)
    premarket_start = datetime.time(4, 0)     # 4:00 AM
    #regular_start = datetime.time(9, 30)      # 9:30 AM
    #regular_end   = datetime.time(16, 0)      # 4:00 PM
    postmarket_end = datetime.time(20, 0)     # 8:00 PM

    # Check if current time falls into any of these windows
    if premarket_start <= now < postmarket_end:
        return True'''
    
    now = datetime.datetime.now(NY).time()
    
    return datetime.time(4, 0) <= now < datetime.time(20, 0)


def is_market_open_today():
    """
    Returns True if today is a valid trading day (excludes weekends and U.S. holidays).
    
    nyse = mcal.get_calendar('NYSE')
    today = pd.Timestamp(datetime.date.today())

    # Get the next valid open date (including today if it's a valid session)
    schedule = nyse.schedule(start_date=today, end_date=today)"""
    nyse = mcal.get_calendar('NYSE')
    today = datetime.datetime.now(NY).strftime('%Y-%m-%d')

    schedule = nyse.schedule(start_date = today, end_date=today)
    return not schedule.empty

# === Crosschecks internal trade status (json) with broker === #

def broker_reconcile(ib, contract, expected_pos, account_id=None):

    if account_id is None:
        accts = ib.managedAccounts()
        account_id = accts[0] if accts else None

    live_qty = 0
    for p in ib.positions():
        if account_id and p.account != account_id:
            continue
        if getattr(p.contract, "conId", None) == getattr(contract, "conId", None):
            live_qty += p.position

    live_pos = 0 if live_qty == 0 else (1 if live_qty > 0 else -1)

    if live_pos != expected_pos:
        msg = (f"Position mismatch for {contract.symbol}: "
               f"live={live_pos} (qty={live_qty}), state={expected_pos}, account={account_id}")

        print(msg)
        log_exception(msg, tz='LOCAL')
        send_email("Position mismatch", msg, email_settings)

        return live_pos, False
    
    return expected_pos, True

def connect_or_retry(ib: IB, host='127.0.0.1', port=7497, base_id=BASE_CLIENT_ID, tries=6):
    cid = base_id
    for n in range(tries):
        try:
            ib.connect(host, port, clientId=cid, timeout=10)
            ib.sleep(0.5)  # allow account/tickers to populate
            print(f"✅ Connected (clientId={cid})")
            return cid
        except Exception as e:
            msg = str(e).lower()
            ib.disconnect()
            if 'client id is already in use' in msg or 'peer closed connection' in msg:
                cid += 1                     # ← auto-bump
            time.sleep(min(60, 2 + 3*n))     # backoff
    raise RuntimeError("Unable to connect after retries.")



# === Main Bot ===

def run_hma200strat8(email_settings, threshold=1.2, log_file='trade_log.csv'):

    paused = False
    last_bar_ts = None

    #runs perpetually while True
    while True:

        try:

            ib = IB()
            try:
                connect_or_retry(ib)
            except Exception as e:
                print(f"❌ Initial connect failed: {e}")
                log_exception(f"Initial connect failed: {e}", tz='LOCAL')
                time.sleep(60)

                continue

            '''#connects to IB server
            print("Connecting to IBKR...")
            ib = IB()
            ib.connect('127.0.0.1', 7497, clientId=1)'''

            #creates contract, pick stock of choice
            contract = Stock(ticker, 'SMART', 'USD')
            [contract] = ib.qualifyContracts(contract)

            #default parameters
            current_position = 0
            entry_type = None
            entry_fill_price = None

            #reads in the last saved position state

                #if the bot crashes, the last active position will be saved in state.
                #load_state() will pull that info

            state = load_state()
            current_position = state['position']
            entry_type = state['entry_type']
            entry_fill_price = state['entry_price']
            paused = state.get('paused', False)

            print("Bot started. Waiting for 15-min intervals...")
            
            #calculates and checks indicators every 15min
        

            while True:

                if paused:
                    print(f"Bot paused at market time {datetime.datetime.now(NY)}."
                          f"Create '{PAUSE_SENTINEL}' to resume.")
                    if os.path.exists(PAUSE_SENTINEL):
                        os.remove(PAUSE_SENTINEL)
                        paused = False
                        print("Resuming Algo...")
                    time.sleep(10)
                    continue


                '''# Check if disconnected from TWS, reconnect if needed
                if not ib.isConnected():
                    print("Reconnecting to IBKR...")
                    try:
                        ib.connect('127.0.0.1', 7497, clientId=1)
                        print("✅ Reconnected.")
                    except Exception as e:
                        retry_count += 1
                        print(f"❌ Reconnection failed: ({retry_count}/{MAX_RECONNECT}) attempts: {e}")
                        log_exception(f"Reconnection failed: {e}", tz='LOCAL')

                        #if tries to reconnect MAX_RECONNECT amount of times, this part stops it
                        if retry_count >= MAX_RECONNECT:
                            print("Max retries reached. Exiting bot.")
                            send_email("hma_200strat8 STOPPED",
                                    f"Bot stopped after {MAX_RECONNECT} failed reconnection attempts.",
                                    email_settings)
                            sys.exit(1)  # exit the script

                        time.sleep(60)
                        continue  # Try again in next loop'''


                now = datetime.datetime.now(NY)

                # Manual override check

                    #create 'manual_override.txt' to stop the script

                if os.path.exists("manual_override.txt"):
                    print("Manual override detected. Stopping bot.")
                    send_email("hma_200strat8 STOPPED", "Bot stopped due to manual override (manual_override.txt found).", email_settings)
                    ib.disconnect()
                    sys.exit(0)  # exits the entire script
                
                # Skip weekends and U.S. holidays
                if not is_market_open_today():
                    print(f" {now.strftime('%Y-%m-%d')} is a holiday or weekend. Skipping.")
                    time.sleep(3600)  # Sleep for 1 hour
                    continue

                if not is_market_open_extended():
                    print("Market is currently closed (extended hours included). Waiting...")
                    time.sleep(3600)
                    continue
                
                bar_ts = floor_to_bar(now, 15)

                #checks if minute is factor of 15: eg. 5:45, 3:15, 9:00 etc.

                if bar_ts != last_bar_ts and now >= bar_ts + datetime.timedelta(seconds=10):

                    last_bar_ts = bar_ts #immediately updates used bar_ts so that process doesn't repeat for the same bar

                    #if now.minute % 15 == 0 and now.second < 15:
                    print(f"\n {now:%Y-%m-%d %H:%M:%S %Z} Checking market...")

                    #retrives the previous days candle bars, calculates indicator values

                    latest, prev = get_hma_strat8_data(ib, contract, end_dt = bar_ts)

                    print("Latest:", latest)
                    print("Previous:", prev)

                    #skips order entry if data could not be read

                    if latest is None or prev is None:
                        print("Skipping this interval due to data issue.")
                        continue

                    # Signal logic
                    long1 = (prev['HMA_diff'] < 0) and (latest['HMA_diff'] > 0) and (latest['HMA_200'] < latest['SMA_300'])
                    long2 = (prev['HMA_diff'] < 0) and (latest['HMA_diff'] > 0) and (latest['HMA_200'] > latest['SMA_300'])
                    short1 = (prev['HMA_diff'] > 0) and (latest['HMA_diff'] < 0) and (latest['HMA_200'] > latest['SMA_300'])
                    short2 = (prev['HMA_diff'] > 0) and (latest['HMA_diff'] < 0) and (latest['HMA_200'] < latest['SMA_300'])
                    
                    #signal is not made yet, it is reset to make judgment further down
                    signal = None
                    if current_position == 0:
                        entry_type = None
                    

                    print(f"Starting Signal: {signal}, Entry type: {entry_type}")

                    # OC reversal exits

                    #For BUY position
                    if current_position == 1 and (latest['oc_pct_change'] < -threshold or latest['gap_pct_change'] < -threshold):
                        
                        #changes signal to get out of BUY position

                        signal = 'SELL'

                        #exits trade IF already in a BUY position (1)

                        exit_trade = Trade(ib, contract, signal)

                        #returns fill price, and boolean for filled

                        filled = exit_trade.fill_and_ensure()
                        ib.sleep(1)

                        #logs, backup, writes, emails, and resets parameters if order filled

                        if filled:
                            
                            #print order status
                            if exit_trade.TEST_MODE:
                                print("[TEST_MODE] Simulated trade — no orderStatus to display.")
                            else:
                                print(exit_trade.trade.orderStatus.status)

                            
        
                            #log trade

                            log_trade(now, 'LONG', entry_type, entry_fill_price, exit_trade.avg_fill_price, exit_trade.filled_qty, exit_trade.total_comm, log_file)
                            backup_file('trade_log.csv', tz='LOCAL')

                            #reset
                            current_position = 0; entry_type = None; entry_fill_price = None
                            
                            #reconcile with broker
                            ib.sleep(1)
                            live_pos, ok = broker_reconcile(ib, contract, expected_pos=0)
                            current_position = live_pos

                            if ok:
                                print("broker reconcilation complete - no issues")
                            else:
                                print("broker reconcilation complete - discrepancy")

                            

                            #saves latest state into state.json

                            write_state(current_position, entry_type, entry_fill_price, paused)

                            #creates message and sends email

                            exit_msg = f"hma_200strat8 exited with a {signal} position at {exit_trade.avg_fill_price} due to OC reversal"
                            print(exit_msg)
                            send_email("NVDA exit", exit_msg, email_settings)

                            time.sleep(60); continue
                        
                        #order not filled
                        else:

                            #manual exit required. 
                            paused = True
                            write_state(current_position, entry_type, entry_fill_price, paused)
                            send_email("hma_200strat8 EXIT ORDER FAILED", f"{signal} order failed to fill.", email_settings)
                            continue

                    #repeats for SELL position        

                    if current_position == -1 and (latest['oc_pct_change'] > threshold or latest['gap_pct_change'] > threshold):
                        
                        #changes signal to get out of BUY position

                        signal = 'BUY'

                        #creates trade and executes

                        exit_trade = Trade(ib, contract, signal)

                        #boolean to check if filled, and order fill price
                        filled = exit_trade.fill_and_ensure()
                        ib.sleep(1)

                        if filled:
                            
                            #print order status

                            if exit_trade.TEST_MODE:
                                print("[TEST_MODE] Simulated trade — no orderStatus to display.")
                            else:
                                print(exit_trade.trade.orderStatus.status)
                            
                            #log trade

                            log_trade(now, 'SHORT', entry_type, entry_fill_price, exit_trade.avg_fill_price, exit_trade.filled_qty, exit_trade.total_comm, log_file)
                            backup_file('trade_log.csv', tz='LOCAL')
                            
                            #reset

                            current_position = 0; entry_type = None; entry_fill_price = None
                        
                            #reconcile with broker
                            ib.sleep(1)
                            live_pos, ok = broker_reconcile(ib, contract, expected_pos=0)
                            current_position = live_pos

                            if ok:
                                print("broker reconcilation complete - no issues")
                            else:
                                print("broker reconcilation complete - discrepancy")
                            
                            

                            #saves position into state.json
                            
                            write_state(current_position, entry_type, entry_fill_price, paused)

                            #creates message and sends email

                            exit_msg = f"hma_200strat8 exited with a {signal} position at {exit_trade.avg_fill_price} due to OC reversal"
                            print(exit_msg)
                            send_email("NVDA exit", exit_msg, email_settings)

                            time.sleep(60); continue
                        
                        #order not filled

                        else:

                            #manual exit required. 
                            paused = True
                            write_state(current_position, entry_type, entry_fill_price, paused)
                            send_email("hma_200strat8 EXIT ORDER FAILED", f"{signal} order failed to fill.", email_settings)
                            continue

                    # Exit logic
                    if current_position == 1:
                        if (entry_type == 'long1' and (latest['HMA_200'] > latest['SMA_300'] or latest['HMA_diff'] < 0)) or \
                           (entry_type == 'long2' and prev['SMA_25'] > prev['HMA_200'] and latest['SMA_25'] < latest['HMA_200']):
                            
                            #changes signal to exit position

                            signal = 'SELL'

                            #creates and executes trade
                            exit_trade = Trade(ib, contract, signal)
                            filled = exit_trade.fill_and_ensure()
                            ib.sleep(1)

                            #same as oc exit

                            if filled:
                                
                                if exit_trade.TEST_MODE:
                                    print("[TEST_MODE] Simulated trade — no orderStatus to display.")
                                else:
                                    print(exit_trade.trade.orderStatus.status)

                                log_trade(now, 'LONG', entry_type, entry_fill_price, exit_trade.avg_fill_price, exit_trade.filled_qty, exit_trade.total_comm, log_file)
                                backup_file('trade_log.csv', tz='LOCAL')

                                exit_msg = f"hma_200strat8 exited {signal} position at {exit_trade.avg_fill_price}"
                                print(exit_msg)
                                send_email("NVDA exit", exit_msg, email_settings)
                            
                                current_position = 0; entry_type = None; entry_fill_price = None

                                #reconcile with broker
                                ib.sleep(1)
                                live_pos, ok = broker_reconcile(ib, contract, expected_pos=0)
                                current_position = live_pos

                                if ok:
                                    print("broker reconcilation complete - no issues")
                                else:
                                    print("broker reconcilation complete - discrepancy")
                                
                                

                                write_state(current_position, entry_type, entry_fill_price, paused)

                            else:

                                paused = True
                                write_state(current_position, entry_type, entry_fill_price, paused)
                                send_email("hma_200strat8 EXIT ORDER FAILED", f"{signal} order failed to fill.", email_settings)
                                continue    

                    if current_position == -1:
                        if (entry_type == 'short1' and (latest['HMA_200'] < latest['SMA_300'] or latest['HMA_diff'] > 0)) or \
                           (entry_type == 'short2' and prev['SMA_25'] < prev['HMA_200'] and latest['SMA_25'] > latest['HMA_200']):

                            signal = 'BUY'

                            exit_trade = Trade(ib, contract, signal)
                            filled = exit_trade.fill_and_ensure()
                            ib.sleep(1)

                             #same as oc exit

                            if filled:
                                
                                if exit_trade.TEST_MODE:
                                    print("[TEST_MODE] Simulated trade — no orderStatus to display.")
                                else:
                                    print(exit_trade.trade.orderStatus.status)

                                log_trade(now, 'SHORT', entry_type, entry_fill_price, exit_trade.avg_fill_price, exit_trade.filled_qty, exit_trade.total_comm, log_file)
                                backup_file('trade_log.csv', tz='LOCAL')

                                exit_msg = f"hma_200strat8 exited {signal} position at {exit_trade.avg_fill_price}"
                                print(exit_msg)
                                send_email("NVDA exit", exit_msg, email_settings)
                            
                                current_position = 0; entry_type = None; entry_fill_price = None

                                #reconcile with broker
                                ib.sleep(1)
                                live_pos, ok = broker_reconcile(ib, contract, expected_pos=0)
                                current_position = live_pos

                                if ok:
                                    print("broker reconcilation complete - no issues")
                                else:
                                    print("broker reconcilation complete - discrepancy")
                                

                                write_state(current_position, entry_type, entry_fill_price, paused)

                            else:

                                paused = True
                                write_state(current_position, entry_type, entry_fill_price, paused)
                                send_email("hma_200strat8 EXIT ORDER FAILED", f"{signal} order failed to fill.", email_settings)
                                continue

                    # Entry logic
                    if current_position == 0:
                        if long1:
                            signal = 'BUY'; entry_type = 'long1'
                        elif long2:
                            signal = 'BUY'; entry_type = 'long2'
                        elif short1:
                            signal = 'SELL'; entry_type = 'short1'
                        elif short2:
                            signal = 'SELL'; entry_type = 'short2'

                        print(f"Indicated Signal: {signal}, Entry type: {entry_type}")

                        
                        if signal in ['BUY', 'SELL'] and entry_type:
                            entry_trade = Trade(ib, contract, signal)
                            filled = entry_trade.fill_and_ensure()

                            ib.sleep(1)

                            if filled:

                                #prints status

                                if entry_trade.TEST_MODE:
                                    print("[TEST_MODE] Simulated trade — no orderStatus to display.")
                                else:
                                    print(entry_trade.trade.orderStatus.status)

                                #sets position parameters

                                current_position = 1 if signal == 'BUY' else -1
                                entry_fill_price = entry_trade.avg_fill_price

                                #expected_pos should be the position bought into, the other expected_pos should be zero bc you're getting out of the trade
                                live_pos, ok = broker_reconcile(ib, contract, expected_pos=current_position) 

                                current_position = live_pos #sets the current position to the actual position IBKR has

                                if ok:
                                    print("broker reconcilation complete - no issues")
                                else:
                                    print("broker reconcilation complete - discrepancy")

                                #writes the updated parameters onto state.json

                                write_state(current_position, entry_type, entry_fill_price, paused)

                                #writes entry message and sends email

                                entry_msg = f"hma_200strat8 entered {signal} at {entry_fill_price}"
                                print(entry_msg)
                                send_email("NVDA entry", entry_msg, email_settings)

                            #order not filled
                            else:
                                 send_email("hma_200strat8 ORDER FAILED", f"{signal} order failed to fill.", email_settings)

                        else:
                            print(f"No valid signal or entry_type (signal={signal}, entry_type={entry_type}) — skipping trade")    
                            #creates and executes trade
                        
                    

                ib.sleep(1)

        #any errors will channel here

        except Exception as e:

            #writes error message and sends email
            msg = f"hma_200strat8 crashed at {datetime.datetime.now()}:\n\n{traceback.format_exc()}"
            print(msg)

            try:
                send_email("hma_200strat8 BOT CRASHED", msg, email_settings)
            
            except Exception as mail_err:
                print(f"Email failed: {mail_err}")

            #logs error onto .csv
            log_exception(msg, tz='LOCAL')  # Log to file

            try:
                for o in ib.openOrders():
                    ib.cancelOrder(o)
                ib.sleep(0.5)
            except Exception:
                pass
            finally:
                try: ib.disconnect()
                except Exception: pass

            time.sleep(60)  # wait before auto-restarting


if __name__ == '__main__':
    run_hma200strat8(email_settings)