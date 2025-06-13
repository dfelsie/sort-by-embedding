import subprocess
import sys
import os
import time

# Define commands
python_server_cmd = [sys.executable, "./unified_sorter_server.py"]
electron_app_cmd = ["npm", "start"]

# Start Python server
print("Starting Python server...")
python_proc = subprocess.Popen(python_server_cmd)

# Optional: wait a moment to let the server spin up
time.sleep(2)

# Start Electron app
print("Starting Electron app...")
electron_proc = subprocess.Popen(electron_app_cmd, shell=True)

try:
    # Keep running until user interrupts
    print("Both processes running. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nShutting down...")

# Cleanup
python_proc.terminate()
electron_proc.terminate()
