# save as gmail_smtp_check.py and run: python gmail_smtp_check.py
import os, smtplib, ssl
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
PORT = int(os.getenv("SMTP_PORT", "465"))
USER = (os.getenv("GMAIL_USER", "") or os.getenv("SMTP_USERNAME", "")).strip()
PASS = (os.getenv("GMAIL_APP_PASSWORD", "") or os.getenv("SMTP_PASSWORD", "")).replace(" ", "").strip()

print(f"Host={HOST}  Port={PORT}")
print(f"User={USER!r}")
print(f"Pass length={len(PASS)} (should be 16)")

try:
    if PORT == 465:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(HOST, PORT, context=ctx, timeout=20) as s:
            print("Connected over SSL")
            s.login(USER, PASS)
            print("LOGIN OK (465/SSL)")
    elif PORT == 587:
        with smtplib.SMTP(HOST, PORT, timeout=20) as s:
            print("Connected over TCP")
            s.ehlo()
            s.starttls(context=ssl.create_default_context())
            print("STARTTLS OK")
            s.login(USER, PASS)
            print("LOGIN OK (587/STARTTLS)")
    else:
        print("Unsupported port (use 465 or 587)")
except smtplib.SMTPAuthenticationError as e:
    print("AUTH ERROR:", getattr(e, "smtp_code", "?"), getattr(e, "smtp_error", b"").decode(errors="ignore"))
except Exception as e:
    print("OTHER ERROR:", repr(e))