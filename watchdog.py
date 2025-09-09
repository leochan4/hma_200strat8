import subprocess
import time
import os


#Create stop_bot.txt to stop the watchdog script

bot_script = "bot.py"  # Replace with your actual bot filename

while True:
    if os.path.exists("stop_bot.txt"):
        print(" Stop file detected. Exiting watchdog.")
        break

    print(" Starting bot...")
    process = subprocess.Popen(["python", bot_script])
    process.wait()

    print(" Bot crashed or exited. Restarting in 60 seconds...")
    time.sleep(60)