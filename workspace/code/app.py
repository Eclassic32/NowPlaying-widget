#!/usr/bin/env python3
# app.py - Flask web server for displaying Windows media information
#
# This script integrates with media_manager.py to display information about
# currently playing media on a local web server.

import threading
import asyncio
import time
import json
from queue import Queue, SimpleQueue
from flask import Flask, render_template, jsonify, request
from media_manager import (
    MediaInfo,
    monitor_media_sessions,
    register_media_change_callback,
    register_timeline_update_callback,
    current_media_info
)

# Initialize Flask app
import os

# Determine the correct paths for templates and static files
# Base directory is one level up from the script location
script_dir = os.path.dirname(os.path.abspath(__file__))  # Get directory where app.py is located
base_dir = os.path.dirname(script_dir)  # Get workspace folder
templates_dir = os.path.join(base_dir, 'templates')
static_dir = os.path.join(base_dir, 'static')

print(f"Script directory: {script_dir}")
print(f"Using templates directory: {templates_dir}")
print(f"Using static directory: {static_dir}")

# Verify that the template directory exists
if not os.path.exists(templates_dir):
    print(f"WARNING: Templates directory not found at {templates_dir}")
    
# Verify that the static directory exists
if not os.path.exists(static_dir):
    print(f"WARNING: Static directory not found at {static_dir}")

app = Flask(__name__, 
           static_folder=static_dir,
           template_folder=templates_dir)

# Global variables to store media information
# Using a lock for thread-safe access to shared data
media_info_lock = threading.Lock()
latest_media_info = None

# Store recent media changes for the nowplaying notification
# We use SimpleQueue for thread-safety to receive changes
media_changes = SimpleQueue()
# And a list to store recent changes for retrieval
recent_changes = []

# Maximum number of media changes to keep in the queue
MAX_CHANGES = 5

# Callback function to handle media changes from media_manager.py
def on_media_change(media_info: MediaInfo):
    """
    Callback function for when media information changes.
    Updates global state and adds to the media changes queue.
    
    Args:
        media_info: The updated MediaInfo object.
    """
    global latest_media_info, recent_changes
    
    with media_info_lock:
        # Handle None media info (stopped/closed media)
        if media_info is None:
            if latest_media_info:
                print("Media stopped, clearing latest_media_info")
                latest_media_info = None
            return
            
        # Only add to changes if there's an actual change
        if not latest_media_info or is_significant_change(latest_media_info, media_info):
            # Update latest media info
            latest_media_info = media_info
            
            # Create change object
            change = {
                "id": int(time.time() * 1000),  # Unique ID based on timestamp
                "info": media_info.as_dict()
            }
            
            # Add to recent_changes list (for API retrieval)
            recent_changes.append(change)
            # Keep only the most recent MAX_CHANGES
            while len(recent_changes) > MAX_CHANGES:
                recent_changes.pop(0)  # Remove oldest
            
            # Also add to the queue for immediate notification
            media_changes.put(change)
        else:
            # Just update the latest_media_info without creating a notification
            latest_media_info = media_info


def is_significant_change(old_info: MediaInfo, new_info: MediaInfo) -> bool:
    """
    Determine if there's a significant change between two MediaInfo objects.
    
    Args:
        old_info: The previous MediaInfo object.
        new_info: The new MediaInfo object.
        
    Returns:
        bool: True if there's a significant change, False otherwise.
    """
    # Check if any of these important properties have changed
    return (old_info.title != new_info.title or
            old_info.artist != new_info.artist or
            old_info.album_title != new_info.album_title or
            old_info.app_name != new_info.app_name or
            old_info.status != new_info.status)

# Callback function to handle timeline updates from media_manager.py
def on_timeline_update(media_info: MediaInfo):
    """
    Callback function for when timeline information updates.
    Only updates the global latest_media_info, doesn't add to the changes queue.
    
    Args:
        media_info: The updated MediaInfo object.
    """
    global latest_media_info
    
    with media_info_lock:
        # Only update timeline-related properties of the existing media_info
        if latest_media_info:
            latest_media_info.current_time_seconds = media_info.current_time_seconds
            latest_media_info.duration_seconds = media_info.duration_seconds
            latest_media_info.timestamp = media_info.timestamp
        else:
            # If there's no existing media_info, create one but don't add to changes
            latest_media_info = media_info

# Start the media monitoring in a separate thread
def start_media_monitor():
    """
    Start the media monitoring loop in a separate thread.
    This runs the asyncio event loop for the media_manager.
    """
    # Create a new event loop for the current thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Store the loop in a global variable so it can be accessed by event handlers
    global monitor_event_loop
    monitor_event_loop = loop
    
    def run_asyncio_loop():
        # Register callbacks
        register_media_change_callback(on_media_change)
        register_timeline_update_callback(on_timeline_update)
        
        # Run the monitor_media_sessions function
        loop.run_until_complete(monitor_media_sessions())
    
    # Start the thread
    monitor_thread = threading.Thread(target=run_asyncio_loop, daemon=True)
    monitor_thread.start()
    return monitor_thread

# Routes

@app.route('/')
def index():
    """
    Index route - redirects to /currentlyplaying
    """
    return '''
    <html>
        <head>
            <title>Windows Media Controller</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    text-align: center;
                }
                h1 {
                    margin-bottom: 30px;
                }
                .links {
                    display: flex;
                    justify-content: center;
                    gap: 20px;
                }
                a {
                    display: inline-block;
                    padding: 10px 20px;
                    background-color: #0078d7;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                }
                a:hover {
                    background-color: #005a9e;
                }
            </style>
        </head>
        <body>
            <h1>Windows Media Controller</h1>
            <div class="links">
                <a href="/currentlyplaying">Currently Playing</a>
                <a href="/nowplaying">Now Playing Notification</a>
            </div>
        </body>
    </html>
    '''

@app.route('/currentlyplaying')
def currently_playing():
    """
    Route for the currently playing media display.
    Renders the currently_playing.html template.
    """
    return render_template('currently_playing.html')

@app.route('/nowplaying')
def now_playing():
    """
    Route for the now playing notification.
    Renders the now_playing_notification.html template.
    """
    return render_template('now_playing_notification.html')

@app.route('/api/current_media')
def current_media():
    """
    API endpoint to get the current media information.
    Returns the latest MediaInfo object as JSON or an error if no media is playing.
    """
    with media_info_lock:
        if latest_media_info:
            # Check if the session is actually playing something meaningful
            # Statuses like 'OPENED' without actual media content shouldn't be displayed
            if (latest_media_info.status in ['OPENED', 'CLOSED', 'STOPPED'] or 
                not latest_media_info.title or 
                latest_media_info.title.strip() == ''):
                print(f"Media info exists but has invalid status: {latest_media_info.status} or empty title")
                
                # Return more detailed error for debugging
                return jsonify({
                    "error": "No active media playing", 
                    "status": latest_media_info.status,
                    "app_name": latest_media_info.app_name,
                    "timestamp": latest_media_info.timestamp
                })
            
            # For Spotify, make an extra check that status is PLAYING or PAUSED
            if "spotify" in latest_media_info.app_name.lower() and latest_media_info.status not in ['PLAYING', 'PAUSED']:
                print(f"Spotify session in invalid state: {latest_media_info.status}")
                
                # Trigger an async refresh to try to recover - this happens via handle_async_callback
                from media_manager import handle_async_callback, update_media_info
                handle_async_callback(update_media_info(force_update=True))
                
                return jsonify({
                    "error": "Spotify not playing active media", 
                    "status": latest_media_info.status,
                    "app_name": latest_media_info.app_name
                })
            
            # Valid media is playing - include app details for easier debugging
            result = latest_media_info.as_dict()
            result["_debug_timestamp"] = time.time()  # Add current time for debugging
            return jsonify(result)
        
        # No media info available
        return jsonify({"error": "No media currently playing", "status": "UNKNOWN"})


@app.route('/api/album_art')
def album_art():
    """
    API endpoint to get the album art for the current media.
    Returns a binary image file or a 404 if no album art is available.
    """
    with media_info_lock:
        if latest_media_info and latest_media_info.thumbnail:
            app_name = latest_media_info.app_name
            is_spotify = "spotify" in app_name.lower()
            
            # Log successful album art retrieval with app name context
            print(f"Serving album art for {app_name} - {latest_media_info.title}, " +
                  f"size: {len(latest_media_info.thumbnail)} bytes" +
                  (", Spotify art (cropped)" if is_spotify else ""))
            
            # Determine content type - default to JPEG
            content_type = "image/jpeg"
            
            # Return the image with appropriate headers
            from flask import Response
            response = Response(latest_media_info.thumbnail, mimetype=content_type)
            # Add cache control headers to improve performance
            response.headers["Cache-Control"] = "public, max-age=60"  # Cache for 60 seconds
            return response
        else:
            # Detailed logging for debugging
            if latest_media_info:
                print(f"Album art requested but not available for {latest_media_info.app_name} - {latest_media_info.title}")
                
                # Special debug info for browser-based apps
                app_name = latest_media_info.app_name.lower()
                if "browser" in app_name or "chrome" in app_name or "edge" in app_name or "firefox" in app_name:
                    print(f"Browser media detected: {latest_media_info.app_name} - Check browser media permissions")
            else:
                print("No media info available when album art was requested")
            
            # Return 404 if no album art is available
            from flask import abort
            return abort(404, description="No album art available")


@app.route('/api/album_art/debug')
def album_art_debug():
    """
    Debug endpoint to show information about the current album art.
    Returns JSON with album art metadata.
    """
    with media_info_lock:
        if latest_media_info and latest_media_info.thumbnail:
            app_name = latest_media_info.app_name
            
            # Get image info
            try:
                from media_manager import analyze_image_format
                image_info = analyze_image_format(latest_media_info.thumbnail)
                
                response = {
                    "app_name": app_name,
                    "title": latest_media_info.title,
                    "artist": latest_media_info.artist,
                    "image_info": image_info,
                    "is_spotify": "spotify" in app_name.lower()
                }
                return jsonify(response)
            except Exception as e:
                return jsonify({
                    "error": str(e),
                    "thumbnail_size": len(latest_media_info.thumbnail) if latest_media_info.thumbnail else 0
                })
        else:
            return jsonify({
                "error": "No album art available",
                "has_media_info": latest_media_info is not None
            })

@app.route('/api/media_changes')
def get_media_changes():
    """
    API endpoint to get recent media changes.
    Returns a list of recent media changes with unique IDs.
    Client can use the last_id parameter to only get changes since their last request.
    """
    last_id = request.args.get('last_id', 0, type=int)
    
    # Get changes that are newer than last_id
    changes = []
    
    with media_info_lock:
        # Filter only changes that are newer than last_id
        changes = [change for change in recent_changes if change["id"] > last_id]
        
        # Send first update if the client has never received any updates and there are no recent changes
        if last_id == 0 and not changes and latest_media_info:
            changes.append({
                "id": int(time.time() * 1000),
                "info": latest_media_info.as_dict()
            })
    
    return jsonify(changes)

def main():
    """
    Main function to start the Flask app and media monitor.
    """
    # Start the media monitor thread
    monitor_thread = start_media_monitor()
    
    # Give the monitor thread a moment to initialize
    time.sleep(1)
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)

if __name__ == '__main__':
    main()