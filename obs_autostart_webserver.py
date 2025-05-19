# obs_autostart_webserver.py
# OBS Python script to start the Windows Media Controller web server in a separate process
# Place this file in your OBS scripts directory and add it via OBS > Tools > Scripts

import obspython as obs
import subprocess
import sys
import os

# Store the process handle globally so we can terminate it if needed
g_webserver_process = None

def script_description():
    return "Automaasdasdasdcally starts the Windows Media Controller web server when OBS launches."

def script_load(settings):
    global g_webserver_process
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Path to your app.py
    app_path = os.path.join(script_dir, "workspace", "code", "app.py")
    # Use the same Python executable as OBS scripting
    python_exe = sys.executable
    # Start the web server in a new process
    g_webserver_process = subprocess.Popen([python_exe, app_path], cwd=os.path.dirname(app_path))
    obs.script_log(obs.LOG_INFO, f"Started web server: {python_exe} {app_path}")

def script_unload():
    global g_webserver_process
    if g_webserver_process is not None:
        g_webserver_process.terminate()
        g_webserver_process = None
        obs.script_log(obs.LOG_INFO, "Stopped web server.")
