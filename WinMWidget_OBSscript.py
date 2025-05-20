# obs_autostart_webserver.py
# OBS Python script to start the Windows Media Controller web server in a separate process
# Place this file in your OBS scripts directory and add it via OBS > Tools > Scripts

import obspython as obs # type: ignore
import subprocess
import sys
import os

# Store the process handle globally so we can terminate it if needed
g_webserver_process = None

def script_description():
    return "Automatically starts the Windows Media Controller web server when OBS launches."

def script_load(settings):
    global g_webserver_process
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(script_dir, "workspace", "code", "app.py")
    python_exe = 'C:/Program Files/Python312/python.exe'
    print(f"Using Python executable: {python_exe}")
    # Start the web server in a new process and capture stdout/stderr
    g_webserver_process = subprocess.Popen(
        [python_exe, app_path],
        cwd=os.path.dirname(app_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
        text=True
    )
    obs.script_log(obs.LOG_INFO, f"Started web server: {python_exe} {app_path} {script_dir}")

    # Read logs in a non-blocking way
    import threading
    def log_reader(proc):
        for line in iter(proc.stdout.readline, ''):
            obs.script_log(obs.LOG_INFO, f"[WebServer] {line.strip()}")
    threading.Thread(target=log_reader, args=(g_webserver_process,), daemon=True).start()

def script_unload():
    global g_webserver_process
    if g_webserver_process is not None:
        g_webserver_process.terminate()
        g_webserver_process = None
        obs.script_log(obs.LOG_INFO, "Stopped web server.")
