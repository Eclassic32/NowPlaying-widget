#!/usr/bin/env python3
# run_app.py - Script to run the Windows Media Controller web server

import sys
import subprocess
import os

# Check if Python is available
python_command = "python"
try:
    subprocess.run([python_command, "--version"], check=True, capture_output=True)
    print("Python found.")
except:
    python_command = "python3"
    try:
        subprocess.run([python_command, "--version"], check=True, capture_output=True)
        print("Python3 found.")
    except:
        print("Error: Python not found. Please install Python 3.9 or higher.")
        sys.exit(1)

# Install dependencies
print("Installing dependencies...")
subprocess.run([python_command, "-m", "pip", "install", "flask", "winrt-Windows.Media.Control", 
                "winrt-Windows.Foundation", "winrt-Windows.Storage.Streams", 
                "winrt-Windows.Foundation.Collections", "winrt-runtime"], check=True)

# Run the app
print("Starting the Windows Media Controller web server...")
print("Access the application at: http://localhost:5000")
print("Press Ctrl+C to stop the server")

# Change to the workspace directory to ensure paths are correct
os.chdir("./workspace")
subprocess.run([python_command, "code/app.py"])