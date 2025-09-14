##############################################################################
#TO DO
#Stay in TESTMODE while I don't have live price streaming. Test code logic first. 
#change reqHistoricalData() to reqMktData() once ready to get live price streaming.

#DONE#   change PnL calculations, as right now the calculation gives negative calculations
#change loop logic so that if the bot crashes, it only retries to connect for an hour. 
#max email send should be 60.
#DONE line 211#    change IBKR password to remove capital letters
#watchdog.py does not work
#check to see if current subscription does give instantaneous price, or if there has to be a delay. 
#consider using POLYGON.io to stream data, and put in trades using IBKR

###############################################################################
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

from trade import Trade
from get_data import get_hma_strat8_data
from state_functions import load_state, write_state



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


# === CSV Logger ===

def log_trade(entry_time, action, entry_type, entry_price, exit_price, filename='trade_log.csv'):

    #calculates PnL on completed trade
    if action == "SHORT":
        pnl = round(entry_price - exit_price, 4)
    elif action == "LONG":
        pnl = round(exit_price - entry_price, 4)
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
        'PnL': pnl
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


# === Exception Log ===

def log_exception(message, filename='error_log.txt'):
    with open(filename, 'a') as f:
        f.write(f"{datetime.datetime.now()}: {message}\n")


# === Backup Log File === #

def backup_file(src_path, backup_dir='backups'):
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    #creates new backup path
    backup_path = os.path.join(backup_dir, f"{os.path.basename(src_path).split('.')[0]}_{timestamp}.csv")
    if os.path.exists(src_path):
        import shutil
        shutil.copy(src_path, backup_path)


# === Checks if market it open === #

def is_market_open_extended():
    """
    Check if current time is within premarket, regular, or postmarket trading hours (Eastern Time).
    Returns True if within any trading window.
    """

    # Current time in US/Eastern timezone
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
        return True
    return False


def is_market_open_today():
    """
    Returns True if today is a valid trading day (excludes weekends and U.S. holidays).
    """
    nyse = mcal.get_calendar('NYSE')
    today = pd.Timestamp(datetime.datetime.now().date(), tz='America/New_York')

    # Get the next valid open date (including today if it's a valid session)
    schedule = nyse.schedule(start_date=today, end_date=today)

    return not schedule.empty


# === Main Bot ===

def run_hma200strat8(email_settings, threshold=1.2, log_file='trade_log.csv'):


    #runs perpetually while True
    while True:

        try:

            #connects to IB server
            ib = IB()
            ib.connect('127.0.0.1', 7497, clientId=1)

            #creates contract, pick stock of choice
            contract = Stock(ticker, 'SMART', 'USD')

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

            print("✅ Bot started. Waiting for 15-min intervals...")
            
            #calculates and checks indicators every 15min
            retry_count = 0
            MAX_RECONNECT = 60

            while True:

                # Check if disconnected from TWS, reconnect if needed
                if not ib.isConnected():
                    print("🔄 Reconnecting to IBKR...")
                    try:
                        ib.connect('127.0.0.1', 7497, clientId=1)
                        print("✅ Reconnected.")
                    except Exception as e:
                        retry_count += 1
                        print(f"❌ Reconnection failed: ({retry_count}/{MAX_RECONNECT}) attempts: {e}")
                        log_exception(f"Reconnection failed: {e}")

                        #if tries to reconnect MAX_RECONNECT amount of times, this part stops it
                        if retry_count >= MAX_RECONNECT:
                            print("Max retries reached. Exiting bot.")
                            send_email("hma_200strat8 STOPPED",
                                    f"Bot stopped after {MAX_RECONNECT} failed reconnection attempts.",
                                    email_settings)
                            sys.exit(1)  # exit the script

                        time.sleep(60)
                        continue  # Try again in next loop


                now = datetime.datetime.now()

                # Manual override check

                    #create 'manual_override.txt' to stop the script

                if os.path.exists("manual_override.txt"):
                    print("Manual override detected. Stopping bot.")
                    send_email("hma_200strat8 STOPPED", "Bot stopped due to manual override (manual_override.txt found).", email_settings)
                    ib.disconnect()
                    sys.exit(0)  # exits the entire script
                
                # Skip weekends and U.S. holidays
                if not is_market_open_today():
                    print(f"📅 {now.strftime('%Y-%m-%d')} is a holiday or weekend. Skipping.")
                    time.sleep(3600)  # Sleep for 1 hour
                    continue

                if not is_market_open_extended():
                    print("Market is currently closed (extended hours included). Waiting...")
                    time.sleep(3600)
                    continue
                

                #checks if minute is factor of 15: eg. 5:45, 3:15, 9:00 etc.

                if now.minute % 15 == 0 and now.second < 15:
                    print(f"\n🕒 {now.strftime('%Y-%m-%d %H:%M:%S')} Checking market...")

                    #retrives the previous days candle bars, calculates indicator values

                    time.sleep(5)

                    latest, prev = get_hma_strat8_data(ib, contract)

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
                    if current_position == 1 and latest['oc_pct_change'] < -threshold:
                        
                        #changes signal to get out of BUY position

                        signal = 'SELL'

                        #exits trade IF already in a BUY position (1)

                        exit_trade = Trade(ib, contract, signal)

                        #returns fill price, and boolean for filled

                        filled, exit_fill_price = exit_trade.fill_and_ensure()
                        ib.sleep(1)

                        #logs, backup, writes, emails, and resets parameters if order filled

                        if filled:
                            
                            #print order status
                            if exit_trade.TEST_MODE:
                                print("[TEST_MODE] Simulated trade — no orderStatus to display.")
                            else:
                                print(exit_trade.trade.orderStatus.status)
        
                            #log trade

                            log_trade(now, 'LONG', entry_type, entry_fill_price, exit_fill_price, log_file)
                            backup_file('trade_log.csv')

                            #reset
                            current_position = 0; entry_type = None; entry_fill_price = None

                            #saves latest state into state.json

                            write_state(current_position, entry_type, entry_fill_price)

                            #creates message and sends email

                            exit_msg = f"hma_200strat8 exited with a {signal} position at {exit_fill_price} due to OC reversal"
                            print(exit_msg)
                            send_email("NVDA exit", exit_msg, email_settings)

                            time.sleep(60); continue
                        
                        #order not filled
                        else:

                            #manual exit required. 

                            send_email("hma_200strat8 ORDER FAILED", f"{signal} order failed to fill.", email_settings)

                    #repeats for SELL position        

                    if current_position == -1 and latest['oc_pct_change'] > threshold:
                        
                        #changes signal to get out of BUY position

                        signal = 'BUY'

                        #creates trade and executes

                        exit_trade = Trade(ib, contract, signal)

                        #boolean to check if filled, and order fill price
                        filled, exit_fill_price = exit_trade.fill_and_ensure()
                        ib.sleep(1)

                        if filled:
                            
                            #print order status

                            if exit_trade.TEST_MODE:
                                print("[TEST_MODE] Simulated trade — no orderStatus to display.")
                            else:
                                print(exit_trade.trade.orderStatus.status)
                            
                            #log trade

                            log_trade(now, 'SHORT', entry_type, entry_fill_price, exit_fill_price, log_file)
                            backup_file('trade_log.csv')
                            
                            #reset

                            current_position = 0; entry_type = None; entry_fill_price = None
                            
                            #saves position into state.json
                            
                            write_state(current_position, entry_type, entry_fill_price)

                            #creates message and sends email

                            exit_msg = f"hma_200strat8 exited with a {signal} position at {exit_fill_price} due to OC reversal"
                            print(exit_msg)
                            send_email("NVDA exit", exit_msg, email_settings)

                            time.sleep(60); continue
                        
                        #order not filled

                        else:

                            #manual exit required. 

                            send_email("hma_200strat8 ORDER FAILED", f"{signal} order failed to fill.", email_settings)


                    # Exit logic
                    if current_position == 1:
                        if (entry_type == 'long1' and (latest['HMA_200'] > latest['SMA_300'] or latest['HMA_diff'] < 0)) or \
                           (entry_type == 'long2' and prev['SMA_25'] > prev['HMA_200'] and latest['SMA_25'] < latest['HMA_200']):
                            
                            #changes signal to exit position

                            signal = 'SELL'

                            #creates and executes trade
                            exit_trade = Trade(ib, contract, signal)
                            filled, exit_fill_price = exit_trade.fill_and_ensure()
                            ib.sleep(1)

                            #same as oc exit

                            if filled:
                                
                                if exit_trade.TEST_MODE:
                                    print("[TEST_MODE] Simulated trade — no orderStatus to display.")
                                else:
                                    print(exit_trade.trade.orderStatus.status)

                                log_trade(now, 'LONG', entry_type, entry_fill_price, exit_fill_price, log_file)
                                backup_file('trade_log.csv')

                                exit_msg = f"hma_200strat8 exited {signal} position at {exit_fill_price}"
                                print(exit_msg)
                                send_email("NVDA exit", exit_msg, email_settings)
                            
                                current_position = 0; entry_type = None; entry_fill_price = None
                                write_state(current_position, entry_type, entry_fill_price)

                            else:
                                send_email("hma_200strat8 ORDER FAILED", f"{signal} order failed to fill.", email_settings)

                    if current_position == -1:
                        if (entry_type == 'short1' and (latest['HMA_200'] < latest['SMA_300'] or latest['HMA_diff'] > 0)) or \
                           (entry_type == 'short2' and prev['SMA_25'] < prev['HMA_200'] and latest['SMA_25'] > latest['HMA_200']):

                            signal = 'BUY'

                            exit_trade = Trade(ib, contract, signal)
                            filled, exit_fill_price = exit_trade.fill_and_ensure()
                            ib.sleep(1)

                             #same as oc exit

                            if filled:
                                
                                if exit_trade.TEST_MODE:
                                    print("[TEST_MODE] Simulated trade — no orderStatus to display.")
                                else:
                                    print(exit_trade.trade.orderStatus.status)

                                log_trade(now, 'SHORT', entry_type, entry_fill_price, exit_fill_price, log_file)
                                backup_file('trade_log.csv')

                                exit_msg = f"hma_200strat8 exited {signal} position at {exit_fill_price}"
                                print(exit_msg)
                                send_email("NVDA exit", exit_msg, email_settings)
                            
                                current_position = 0; entry_type = None; entry_fill_price = None
                                write_state(current_position, entry_type, entry_fill_price)

                            else:
                                send_email("hma_200strat8 ORDER FAILED", f"{signal} order failed to fill.", email_settings)

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
                            filled, entry_fill_price = entry_trade.fill_and_ensure()

                            ib.sleep(1)

                            if filled:

                                #prints status

                                if entry_trade.TEST_MODE:
                                    print("[TEST_MODE] Simulated trade — no orderStatus to display.")
                                else:
                                    print(entry_trade.trade.orderStatus.status)

                                #sets position parameters

                                current_position = 1 if signal == 'BUY' else -1

                                #writes the updated parameters onto state.json

                                write_state(current_position, entry_type, entry_fill_price)

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
                        
            

                            
                    
                            

                    time.sleep(60)
                time.sleep(10)

        #any errors will channel here

        except Exception as e:

            #writes error message and sends email
            msg = f"hma_200strat8 crashed at {datetime.datetime.now()}:\n\n{traceback.format_exc()}"
            print(msg)
            send_email("hma_200strat8 BOT CRASHED", msg, email_settings)
            
            #logs error onto .csv
            log_exception(msg)  # Log to file



            time.sleep(60)  # wait before auto-restarting


if __name__ == '__main__':
    run_hma200strat8(email_settings)