from ib_insync import *
import pandas as pd
import numpy as np
import time
import datetime
import os
import traceback
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv(dotenv_path='c:/Users/lsuen/OneDrive/Desktop/hma_200strat8/.env')

email_settings = {
    'sender': os.getenv('EMAIL_SENDER'),
    'recipient': os.getenv('EMAIL_RECIPIENT'),
    'smtp_server': os.getenv('SMTP_SERVER'),
    'smtp_port': int(os.getenv('SMTP_PORT')),
    'username': os.getenv('EMAIL_SENDER'),
    'password': os.getenv('EMAIL_PASSWORD')
}

def send_email(subject, body, config):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = config['sender']
    msg['To'] = config['recipient']

    try:
        with smtplib.SMTP_SSL(config['smtp_server'], config['smtp_port']) as server:
            server.login(config['username'], config['password'])
            server.send_message(msg)
    except Exception as e:
        print(f"Email failed: {e}")

try:
    1 / 0  # Simulated error (division by zero)
except Exception:
    msg = f"⚠️ hma_200strat8 crashed at {datetime.datetime.now()}:\n\n{traceback.format_exc()}"
    print(msg)
    send_email("hma_200strat8 BOT CRASHED", msg, email_settings)
