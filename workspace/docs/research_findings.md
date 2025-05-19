# Research Findings: Accessing Windows Media Information with pywinrt

This document summarizes the research on using `pywinrt` to access and monitor Windows media playback information, focusing on the `Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager` API.

## 1. Primary Library: `pywinrt`

### Installation
To use `pywinrt` for Windows Media Control, you need to install the following packages using pip. Python 3.9 or higher is required.

```bash
pip install winrt-runtime
pip install winrt-Windows.Media.Control
pip install winrt-Windows.Foundation # Often needed for async operations and types like TimeSpan
```
It's also good practice to ensure `asyncio` is available, which is standard with Python 3.7+.

### Core Imports
The primary classes and enums will be imported from `winrt.windows.media.control` and `winrt.windows.foundation`.

```python
import asyncio
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSession as MediaSession,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus
)
from winrt.windows.foundation import TimeSpan # For handling duration and position
# Potentially other imports like IAsyncOperation if dealing with low-level async patterns
```

### Basic Code Structure to Get Current Media Session
Accessing media information is an asynchronous operation.

```python
async def get_current_media_session():
    '''
    Retrieves the current media session manager and the current media session.
    Returns None if no session manager or current session is available.
    '''
    try:
        # Request the media manager asynchronously
        manager = await MediaManager.request_async()
        if manager:
            # Get the current session
            current_session = manager.get_current_session()
            return manager, current_session
        return None, None
    except Exception as e:
        print(f"Error getting media session: {e}")
        return None, None

async def main_example_get_session():
    manager, current_session = await get_current_media_session()
    if current_session:
        print(f"Successfully retrieved current session: {current_session.source_app_user_model_id}")
        # Further operations on current_session would go here
    else:
        print("No current media session found or error occurred.")

# To run this example:
# asyncio.run(main_example_get_session())
```

## 2. Information Extraction from Media Session

Once you have a `current_session` object (an instance of `GlobalSystemMediaTransportControlsSession`), you can extract various pieces of information.

### Song Title, Main Artist, Album/Playlist
This information is available through the media properties of the session.

```python
async def get_media_properties(session: MediaSession):
    '''
    Retrieves media properties (title, artist, album) from the session.
    '''
    if not session:
        return None
    try:
        # Get media properties asynchronously
        properties = await session.try_get_media_properties_async()
        if properties:
            media_info = {
                "title": properties.title,
                "artist": properties.artist,
                "album_title": properties.album_title,
                "album_artist": properties.album_artist,
                "track_number": properties.track_number
                # properties.subtitle_text might also be available
                # For playlists, specific properties might not be directly available here,
                # it might be part of the title or a different property if the source provides it.
            }
            return media_info
        return None
    except Exception as e:
        print(f"Error getting media properties: {e}")
        return None

# Example usage within an async function:
# if current_session:
#     media_props = await get_media_properties(current_session)
#     if media_props:
#         print(f"Title: {media_props['title']}, Artist: {media_props['artist']}")
```
*Note: The exact available properties (e.g., playlist name) might depend on what the media source application provides.*

### Application Playing the Media (`SourceAppUserModelId` / Display Name)
The session object has a `source_app_user_model_id` attribute.

```python
# (Inside an async function where 'current_session' is available)
# if current_session:
#     app_id = current_session.source_app_user_model_id
#     print(f"Source App User Model ID: {app_id}")
```
Getting a user-friendly display name from the `SourceAppUserModelId` in Python directly with `pywinrt` was not explicitly found in the research. C++/C# examples show using platform APIs like `AppDisplayInfo.DisplayName` or custom functions. A similar approach might be needed in Python, potentially involving other `winrt` namespaces or a different library if `pywinrt` doesn't expose a direct conversion.

### Playback Status (Playing, Paused, Stopped)
The playback status is obtained via the `get_playback_info()` method.

```python
def get_playback_status_info(session: MediaSession):
    '''
    Retrieves playback information, including status.
    This is a synchronous call on the session object.
    '''
    if not session:
        return None
    try:
        playback_info = session.get_playback_info()
        if playback_info:
            status = playback_info.playback_status # This is an enum
            status_str = "Unknown"
            if status == PlaybackStatus.PLAYING:
                status_str = "Playing"
            elif status == PlaybackStatus.PAUSED:
                status_str = "Paused"
            elif status == PlaybackStatus.STOPPED:
                status_str = "Stopped"
            elif status == PlaybackStatus.CLOSED:
                status_str = "Closed"
            elif status == PlaybackStatus.OPENED: # Media source is open
                status_str = "Opened"
            elif status == PlaybackStatus.CHANGED: # Playback rate/shuffle/auto-repeat changed
                status_str = "Changed"

            controls_info = {
                "can_pause": playback_info.controls.is_pause_enabled,
                "can_play": playback_info.controls.is_play_enabled,
                "can_stop": playback_info.controls.is_stop_enabled,
                "can_change_next": playback_info.controls.is_next_enabled,
                "can_change_previous": playback_info.controls.is_previous_enabled,
            }
            return {"status_enum": status, "status_str": status_str, "controls": controls_info}
        return None
    except Exception as e:
        # Catching generic Exception, specific WinRTError could be caught too.
        # Sometimes, if a media app is in a weird state, this call can fail.
        print(f"Error getting playback info: {e}")
        return None

# Example usage (can be called synchronously if session is available):
# if current_session:
#     playback_details = get_playback_status_info(current_session)
#     if playback_details:
#         print(f"Playback Status: {playback_details['status_str']}")
```

### Timeline Information (Current Position, Total Duration)
Timeline information is obtained via `get_timeline_properties()`.

```python
def get_timeline_info(session: MediaSession):
    '''
    Retrieves timeline properties (position, duration).
    This is a synchronous call on the session object.
    '''
    if not session:
        return None
    try:
        timeline_props = session.get_timeline_properties()
        if timeline_props:
            # TimeSpan objects are typically represented in 100-nanosecond units (ticks).
            # Convert to seconds: ticks / 10,000,000
            current_position_seconds = timeline_props.position.duration / 10_000_000
            start_time_seconds = timeline_props.start_time.duration / 10_000_000
            end_time_seconds = timeline_props.end_time.duration / 10_000_000
            # Total duration can be end_time - start_time, or often end_time if start_time is 0.
            total_duration_seconds = end_time_seconds

            return {
                "current_position_sec": current_position_seconds,
                "total_duration_sec": total_duration_seconds,
                "start_time_sec": start_time_seconds,
                "end_time_sec": end_time_seconds,
                "last_updated_time_raw": timeline_props.last_updated_time # This is a DateTimeOffset
            }
        return None
    except Exception as e:
        print(f"Error getting timeline properties: {e}")
        return None

# Example usage (can be called synchronously if session is available):
# if current_session:
#     timeline = get_timeline_info(current_session)
#     if timeline:
#         print(f"Position: {timeline['current_position_sec']:.2f}s / {timeline['total_duration_sec']:.2f}s")

```
*Note: `TimeSpan` objects from `winrt.windows.foundation` have a `duration` attribute which is an `int64` representing 100-nanosecond intervals.*

## 3. Change Detection (Event Handling)

`pywinrt` allows for event handling, which is preferred over polling. Events are typically handled in an `asyncio` environment. The general pattern is `object.add_eventname(handler_function)` and `object.remove_eventname(handler_function)`.

### Detecting New Song or Playback State Changes
This involves handling events from both the `MediaManager` (for session changes) and the `MediaSession` itself (for property/playback changes within the current session).

**Global Session Change (`current_session_changed` on the manager):**

```python
# (global manager object assumed to be initialized via MediaManager.request_async())
# manager = await MediaManager.request_async()

def on_current_session_changed(sender, args):
    # This handler will be called when the system's current media session changes
    # (e.g., user switches from Spotify to VLC).
    # You might need to re-fetch the current session and attach new listeners.
    print("Current media session changed!")
    # Need to run async code to get new session and its properties
    # This often involves scheduling a new task in the asyncio loop or using call_soon_threadsafe
    # if the event fires on a different thread.
    # For simplicity, just printing here.
    new_session = sender.get_current_session() # The sender is the manager
    if new_session:
        print(f"New session source: {new_session.source_app_user_model_id}")
        # Here you would typically attach property change listeners to 'new_session'
    else:
        print("Current session is now None.")


# Attaching the event handler (assuming 'manager' is available):
# if manager:
#     manager.add_current_session_changed(on_current_session_changed)
#     print("Attached current_session_changed handler.")

# Keep the script running to listen for events (e.g., asyncio.get_event_loop().run_forever())
```

**Media Property Changes within a Session (`media_properties_changed`, `playback_info_changed`, `timeline_properties_changed` on the session):**

```python
# (current_session object assumed to be available)

def on_media_properties_changed(session_sender, args):
    # This handler is called when title, artist, album, etc., change for the current_session.
    print(f"Media properties changed for session: {session_sender.source_app_user_model_id}")
    # You would re-fetch media properties here:
    # loop = asyncio.get_running_loop()
    # loop.create_task(get_media_properties(session_sender)) # Example

def on_playback_info_changed(session_sender, args):
    # This handler is called when play/pause state, controls availability, etc., change.
    print(f"Playback info changed for session: {session_sender.source_app_user_model_id}")
    # playback_details = get_playback_status_info(session_sender)
    # if playback_details: print(f"New status: {playback_details['status_str']}")

def on_timeline_properties_changed(session_sender, args):
    print(f"Timeline properties changed for session: {session_sender.source_app_user_model_id}")
    # timeline = get_timeline_info(session_sender)
    # if timeline: print(f"New position: {timeline['current_position_sec']:.2f}s")


# Attaching event handlers to a specific session:
# if current_session:
#     current_session.add_media_properties_changed(on_media_properties_changed)
#     current_session.add_playback_info_changed(on_playback_info_changed)
#     current_session.add_timeline_properties_changed(on_timeline_properties_changed)
#     print(f"Attached event listeners to session {current_session.source_app_user_model_id}")

```
*Note: Python-specific examples for event handling with `GlobalSystemMediaTransportControlsSessionManager` were not directly found in abundance. The patterns above are based on general `pywinrt` event handling (as seen in its GitHub examples for other APIs like `MediaPlayer`) and the documented events for the C#/.NET counterparts. Careful management of the `asyncio` event loop and thread safety (if events are fired from non-Python threads) is crucial.*

## 4. Key Considerations and Notes

*   **Asynchronous Nature**: Most interactions with `pywinrt`, especially initializations and property fetching, are asynchronous. `asyncio` is essential.
*   **Error Handling**: Calls to WinRT APIs can fail, especially if media applications are not behaving well or if permissions are missing. Robust `try...except` blocks are recommended. Specific `WinRTError` exceptions can be caught.
*   **Enum Values**: Playback status and other states are often represented by enums. Refer to `winrt.windows.media.control` for specific enum members.
*   **TimeSpans**: Durations and positions are `TimeSpan` objects, typically representing 100-nanosecond intervals. Convert them to seconds or other units as needed.
*   **Event Loop Management**: For event-driven scripts, the `asyncio` event loop must be kept running (e.g., `loop.run_forever()`).
*   **Detaching Handlers**: Remember to `remove_eventname(handler)` when a session is no longer valid or the application is shutting down to prevent memory leaks or errors.
*   **Completeness of Information**: The information provided by media applications can vary. Some apps might not provide all properties (e.g., album art, subtitle).
*   **Inferred Python Examples**: Some Python code snippets, particularly for event handling details and `SourceAppUserModelId` to display name conversion, are based on `pywinrt` conventions and C#/C++ documentation due to a lack of direct, comprehensive Python examples found during research. Further experimentation might be needed.

This research should provide a strong foundation for developing a Python script to interact with Windows media information using `pywinrt`.
