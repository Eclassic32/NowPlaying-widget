#!/usr/bin/env python3
# media_manager.py - Windows Media Information Monitor
#
# A script that monitors and retrieves information about currently playing media
# on Windows using the Windows Media Control API via pywinrt

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, List, Set, Coroutine
import threading

# Import pywinrt modules
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    GlobalSystemMediaTransportControlsSession as MediaSession,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus
)
from winrt.windows.storage.streams import DataReader
# TimeSpan is not needed, using timedelta properties instead

# Global variable to store the event loop that's running in the monitor thread
monitor_event_loop = None

def handle_async_callback(coro: Coroutine):
    """
    Helper function to properly schedule a coroutine in the monitor's event loop.
    This avoids the "no running event loop" error.
    
    Args:
        coro: The coroutine to schedule.
    """
    if monitor_event_loop is None:
        print("Warning: Monitor event loop not initialized, callback skipped.")
        return
        
    if threading.current_thread() is threading.main_thread():
        # If we're in the main thread, we need to use the monitor's event loop
        asyncio.run_coroutine_threadsafe(coro, monitor_event_loop)
    else:
        # If we're already in the monitor thread with the right loop
        try:
            current_loop = asyncio.get_running_loop()
            if current_loop == monitor_event_loop:
                asyncio.create_task(coro)
            else:
                asyncio.run_coroutine_threadsafe(coro, monitor_event_loop)
        except RuntimeError:
            # No event loop running in this thread
            asyncio.run_coroutine_threadsafe(coro, monitor_event_loop)


@dataclass
class MediaInfo:
    """Class to store information about currently playing media."""
    title: str = ""
    artist: str = ""
    album_title: str = ""
    app_name: str = ""  # Display name or SourceAppUserModelId
    status: str = "UNKNOWN"  # PLAYING, PAUSED, STOPPED, UNKNOWN
    current_time_seconds: float = 0.0
    duration_seconds: float = 0.0
    thumbnail: Optional[bytes] = None
    timestamp: float = field(default_factory=time.time)  # Timestamp of when info was retrieved
    additional_artists: List[str] = field(default_factory=list)
    
    def as_dict(self) -> Dict[str, Any]:
        """Convert the MediaInfo object to a dictionary."""
        result = {
            "title": self.title,
            "artist": self.artist,
            "album_title": self.album_title,
            "app_name": self.app_name,  # Using original app name instead of friendly name
            "status": self.status,
            "current_time_seconds": self.current_time_seconds,
            "duration_seconds": self.duration_seconds,
            "additional_artists": self.additional_artists,
            "timestamp": self.timestamp,
            "has_thumbnail": self.thumbnail is not None
            # Exclude thumbnail from dict as it's binary data
        }
        return result


# Global variables for keeping track of state
current_media_info: Optional[MediaInfo] = None
media_change_callbacks: Set[Callable[[MediaInfo], None]] = set()
timeline_update_callbacks: Set[Callable[[MediaInfo], None]] = set()
registered_event_tokens = {}  # Keep track of event registrations to unregister later

# Cache for thumbnails to avoid fetching them repeatedly
thumbnail_cache = {
    # Structure: { "app_name:title:artist": thumbnail_bytes }
}


def analyze_image_format(image_bytes):
    """
    Analyze the format and dimensions of an image from its bytes.
    This is a utility function for debugging thumbnail processing.
    
    Args:
        image_bytes: The image data as bytes.
        
    Returns:
        dict: Information about the image format and dimensions.
    """
    try:
        from io import BytesIO
        from PIL import Image
        
        img = Image.open(BytesIO(image_bytes))
        return {
            "format": img.format,
            "mode": img.mode,
            "width": img.width,
            "height": img.height,
            "size_bytes": len(image_bytes)
        }
    except Exception as e:
        return {
            "error": str(e),
            "size_bytes": len(image_bytes) if image_bytes else 0
        }


async def get_media_manager() -> Optional[MediaManager]:
    """
    Get the GlobalSystemMediaTransportControlsSessionManager instance.
    
    Returns:
        MediaManager or None: The media manager instance or None if error occurs.
    """
    try:
        return await MediaManager.request_async()
    except Exception as e:
        print(f"Error getting media manager: {e}")
        return None


def get_current_session(manager: Optional[MediaManager]) -> Optional[MediaSession]:
    """
    Get the current active media session from the manager.
    
    Args:
        manager: The media manager instance.
        
    Returns:
        MediaSession or None: The current media session or None if no session is active.
    """
    if not manager:
        return None
    
    try:
        return manager.get_current_session()
    except Exception as e:
        print(f"Error getting current session: {e}")
        return None


async def get_media_properties(session: Optional[MediaSession]) -> Optional[Dict[str, Any]]:
    """
    Get media properties from the current session.
    
    Args:
        session: The current media session.
        
    Returns:
        dict or None: Dictionary containing media properties or None if error occurs.
    """
    if not session:
        return None
    
    try:
        properties = await session.try_get_media_properties_async()
        if not properties:
            return None
        
        media_info = {
            "title": properties.title,
            "artist": properties.artist,
            "album_title": properties.album_title,
            "album_artist": properties.album_artist,
            "track_number": properties.track_number,
            # Additional artists might be in other fields depending on the media application
            "additional_info": ""  # Removed subtitle_text reference as it's not accessible
        }
        return media_info
    
    except Exception as e:
        print(f"Error getting media properties: {e}")
        return None


def get_playback_status(session: Optional[MediaSession]) -> Optional[Dict[str, Any]]:
    """
    Get playback status information from the current session.
    
    Args:
        session: The current media session.
        
    Returns:
        dict or None: Dictionary containing playback status or None if error occurs.
    """
    if not session:
        return None
    
    try:
        playback_info = session.get_playback_info()
        if not playback_info:
            return None
        
        status = playback_info.playback_status
        status_str = "UNKNOWN"
        
        if status == PlaybackStatus.PLAYING:
            status_str = "PLAYING"
        elif status == PlaybackStatus.PAUSED:
            status_str = "PAUSED"
        elif status == PlaybackStatus.STOPPED:
            status_str = "STOPPED"
        elif status == PlaybackStatus.CLOSED:
            status_str = "CLOSED"
        elif status == PlaybackStatus.OPENED:
            status_str = "OPENED"
        elif status == PlaybackStatus.CHANGING:
            status_str = "CHANGING"
        
        controls_info = {
            "can_pause": playback_info.controls.is_pause_enabled,
            "can_play": playback_info.controls.is_play_enabled,
            "can_stop": playback_info.controls.is_stop_enabled,
            "can_next": playback_info.controls.is_next_enabled,
            "can_previous": playback_info.controls.is_previous_enabled
        }
        
        return {"status": status_str, "controls": controls_info}
    
    except Exception as e:
        print(f"Error getting playback status: {e}")
        return None


def get_timeline_info(session: Optional[MediaSession]) -> Optional[Dict[str, float]]:
    """
    Get timeline information from the current session.
    
    Args:
        session: The current media session.
        
    Returns:
        dict or None: Dictionary containing timeline information or None if error occurs.
    """
    if not session:
        return None
    
    try:
        timeline_props = session.get_timeline_properties()
        if not timeline_props:
            return None
        
        # Convert timedelta objects to seconds using total_seconds()
        current_position_seconds = timeline_props.position.total_seconds()
        start_time_seconds = timeline_props.start_time.total_seconds()
        end_time_seconds = timeline_props.end_time.total_seconds()
        
        # In most cases, total duration is end_time - start_time
        total_duration_seconds = end_time_seconds - start_time_seconds
        
        # Some apps might set only end_time
        if total_duration_seconds <= 0 and end_time_seconds > 0:
            total_duration_seconds = end_time_seconds
        
        return {
            "current_position_seconds": current_position_seconds,
            "total_duration_seconds": total_duration_seconds,
            "start_time_seconds": start_time_seconds,
            "end_time_seconds": end_time_seconds
        }
    
    except Exception as e:
        print(f"Error getting timeline info: {e}")
        return None


async def get_thumbnail(session: Optional[MediaSession], media_props: Optional[Dict[str, Any]] = None) -> Optional[bytes]:
    """
    Get the thumbnail (album art) from the current session.
    
    Args:
        session: The current media session.
        media_props: Optional media properties to use for cache key generation.
        
    Returns:
        bytes or None: The thumbnail image data as bytes, or None if not available.
    """
    if not session:
        print("No session available for thumbnail retrieval")
        return None
    
    try:
        app_name = session.source_app_user_model_id
        
        # Get media properties if not provided
        if not media_props:
            properties = await session.try_get_media_properties_async()
            if not properties:
                print("No properties available")
                return None
                
            title = properties.title
            artist = properties.artist
        else:
            title = media_props.get("title", "")
            artist = media_props.get("artist", "")
        
        # Generate cache key - include app name to differentiate between sources
        cache_key = f"{app_name}:{title}:{artist}"
        
        # Check cache first
        if cache_key in thumbnail_cache:
            print(f"Using cached thumbnail for {cache_key}")
            return thumbnail_cache[cache_key]
            
        print(f"Attempting to get thumbnail for {app_name} - {title}")
        
        # Always get fresh properties for the thumbnail
        # This is important for browser-based apps and non-Spotify sources
        properties = await session.try_get_media_properties_async()
        if not properties:
            print("No properties available")
            return None
        
        # Ensure the thumbnail exists (more explicit check for debugging)
        if not properties.thumbnail:
            print(f"No thumbnail available in properties for {app_name}")
            return None
        
        # More detailed debugging for browser-based apps
        if "browser" in app_name.lower() or "chrome" in app_name.lower() or "edge" in app_name.lower() or "firefox" in app_name.lower():
            print(f"Browser media detected: {app_name} - Thumbnail exists: {properties.thumbnail is not None}")
        
        # Get the thumbnail stream
        thumbnail_stream = await properties.thumbnail.open_read_async()
        if not thumbnail_stream:
            print(f"Failed to open thumbnail stream for {app_name}")
            return None
        
        size = thumbnail_stream.size
        if size == 0:
            print(f"Thumbnail stream is empty for {app_name}")
            return None
            
        print(f"Thumbnail stream opened for {app_name}, size: {size} bytes")
        
        # Read the thumbnail data
        try:
            data_reader = DataReader(thumbnail_stream)
            buffer = await data_reader.load_async(size)
            
            # Read bytes from buffer into a Python bytearray
            result = bytearray(size)
            for i in range(size):
                result[i] = data_reader.read_byte()
            
            # Close the streams
            data_reader.close()
            thumbnail_stream.close()
            
            # Store original thumbnail
            thumbnail_bytes = bytes(result)                # Process Spotify album art - crop to 234x234 starting at (33,0)
            if "spotify" in app_name.lower():
                try:
                    from io import BytesIO
                    from PIL import Image
                    
                    # Convert bytes to an image
                    img_buffer = BytesIO(thumbnail_bytes)
                    img = Image.open(img_buffer)
                    
                    # Get image dimensions
                    width, height = img.size
                    print(f"Original Spotify image size: {width}x{height}, format: {img.format}")
                    
                    # Only crop if the image is large enough
                    if width >= 33 + 234 and height >= 234:
                        # Crop the image (left, top, right, bottom)
                        cropped = img.crop((33, 0, 33 + 234, 234))
                        
                        # Save the cropped image to bytes with high quality
                        output_buffer = BytesIO()
                        format_to_use = img.format or "JPEG"
                        
                        if format_to_use == "JPEG":
                            # Use high quality for JPEG
                            cropped.save(output_buffer, format=format_to_use, quality=95)
                        else:
                            # For PNG and other formats, use default settings
                            cropped.save(output_buffer, format=format_to_use)
                            
                        thumbnail_bytes = output_buffer.getvalue()
                        
                        # Check the result
                        cropped_img = Image.open(BytesIO(thumbnail_bytes))
                        print(f"Successfully cropped Spotify thumbnail to {cropped_img.width}x{cropped_img.height}")
                    else:
                        print(f"Spotify image too small to crop: {width}x{height}")
                        
                except Exception as e:
                    print(f"Error processing Spotify image: {e}")
                    # Fall back to original image if processing fails
            
            # Store in cache
            thumbnail_cache[cache_key] = thumbnail_bytes
            
            # Limit cache size
            if len(thumbnail_cache) > 20:  # Increased cache size to 20 for more apps
                oldest_key = next(iter(thumbnail_cache))
                del thumbnail_cache[oldest_key]
            
            print(f"Successfully cached thumbnail for {app_name} - {title} ({len(thumbnail_bytes)} bytes)")
            return thumbnail_bytes
            
        except Exception as e:
            print(f"Error reading thumbnail data for {app_name}: {e}")
            if thumbnail_stream:
                thumbnail_stream.close()
            return None
            
    except Exception as e:
        print(f"Error getting thumbnail for {app_name}: {e}")
        return None


async def get_current_media_info() -> Optional[MediaInfo]:
    """
    Get all current media information combined into a MediaInfo object.
    
    Returns:
        MediaInfo or None: Object containing all media information or None if no media is playing.
    """
    manager = await get_media_manager()
    session = get_current_session(manager)
    
    if not session:
        return None
    
    media_props = await get_media_properties(session)
    playback_info = get_playback_status(session)
    timeline_info = get_timeline_info(session)
    
    if not (media_props and playback_info):
        return None
    
    # Get app name - for now we use the SourceAppUserModelId
    # In a more comprehensive solution, this could be mapped to friendly names
    app_name = session.source_app_user_model_id
    
    media_info = MediaInfo(
        title=media_props.get("title", ""),
        artist=media_props.get("artist", ""),
        album_title=media_props.get("album_title", ""),
        app_name=app_name,
        status=playback_info.get("status", "UNKNOWN")
    )
    
    # Add timeline information if available
    if timeline_info:
        media_info.current_time_seconds = timeline_info.get("current_position_seconds", 0.0)
        media_info.duration_seconds = timeline_info.get("total_duration_seconds", 0.0)
    
    # Try to get the thumbnail
    try:
        thumbnail_data = await get_thumbnail(session, media_props)
        if thumbnail_data:
            media_info.thumbnail = thumbnail_data
    except Exception as e:
        print(f"Error getting thumbnail: {e}")
    
    # Set the timestamp to current time
    media_info.timestamp = time.time()
    
    # Since we no longer have additional_info from subtitle_text,
    # we'll leave the additional_artists as an empty list
    media_info.additional_artists = []
    
    return media_info


# Event handler functions
async def sessions_changed_handler(manager, args):
    """
    Handler for when the available media sessions change.
    
    Args:
        manager: The media manager instance.
        args: Event arguments.
    """
    global current_media_info, registered_event_tokens
    
    print("Media sessions changed - checking for new current session")
    
    try:
        # Get the new current session
        new_session = manager.get_current_session()
        
        # Try to get all sessions to check if Spotify is available but not active
        try:
            all_sessions = manager.get_sessions()
            
            # Look for Spotify specifically
            spotify_session = None
            for session in all_sessions:
                try:
                    app_id = session.source_app_user_model_id
                    if "spotify" in app_id.lower():
                        print(f"Found Spotify session: {app_id}")
                        spotify_session = session
                        # Don't break, as we want to see all sessions
                except Exception as e:
                    print(f"Error checking session: {e}")
            
            # Debug log all sessions found
            print(f"Found {len(all_sessions)} media sessions:")
            for session in all_sessions:
                try:
                    print(f"  - {session.source_app_user_model_id}")
                except:
                    print("  - [Unnamed Session]")
                    
            # If new_session is None but Spotify session exists, use it
            if not new_session and spotify_session:
                print("No active session but Spotify available - using it")
                new_session = spotify_session
                
        except ImportError:
            print("Warning: Collections module not available, cannot get all sessions")
            # If we can't get all sessions, we'll work with just the current session
            all_sessions = []
            spotify_session = None
        except Exception as e:
            print(f"Error getting all sessions: {e}")
            all_sessions = []
            spotify_session = None
        
        # Unregister events from any previous session
        if "session" in registered_event_tokens:
            old_session = registered_event_tokens["session"].get("session_obj")
            if old_session:
                # Unregister event handlers
                for event_name, token in registered_event_tokens["session"].items():
                    if event_name != "session_obj":  # Skip non-token entries
                        try:
                            event_remove_method = getattr(old_session, f"remove_{event_name}")
                            event_remove_method(token)
                            print(f"Unregistered {event_name} handler from old session")
                        except Exception as e:
                            print(f"Error unregistering {event_name} handler: {e}")
        
        # Clear registered tokens for the session
        registered_event_tokens["session"] = {"session_obj": new_session}
        
        # If we're currently playing from Spotify but current session changes to something else,
        # and we can still find Spotify, keep the Spotify session as a fallback
        if current_media_info and "spotify" in current_media_info.app_name.lower() and spotify_session and new_session:
            try:
                if "spotify" not in str(new_session.source_app_user_model_id).lower():
                    print("Session switched away from Spotify, but Spotify session still exists. Adding Spotify as backup.")
                    registered_event_tokens["spotify_session"] = {"session_obj": spotify_session}
            except Exception as e:
                print(f"Error comparing session app IDs: {e}")
        
        if new_session:
            # Register event handlers for the new session
            try:
                token = new_session.add_media_properties_changed(
                    lambda s, a: handle_async_callback(media_properties_changed_handler(s, a))
                )
                registered_event_tokens["session"]["media_properties_changed"] = token
                
                token = new_session.add_playback_info_changed(
                    lambda s, a: handle_async_callback(playback_info_changed_handler(s, a))
                )
                registered_event_tokens["session"]["playback_info_changed"] = token
                
                token = new_session.add_timeline_properties_changed(
                    lambda s, a: handle_async_callback(timeline_properties_changed_handler(s, a))
                )
                registered_event_tokens["session"]["timeline_properties_changed"] = token
                
                app_id = "[Unknown]"
                try:
                    app_id = new_session.source_app_user_model_id
                except:
                    pass
                print(f"Registered event handlers for new session: {app_id}")
                
                # For Spotify sessions, set the timestamp to indicate we have a fresh connection
                if "spotify" in str(app_id).lower():
                    print("Fresh Spotify session detected - marking as new connection")
                    # This will help the UI know to refresh thumbnails
                    if current_media_info and "spotify" in current_media_info.app_name.lower():
                        current_media_info.timestamp = time.time()
            except Exception as e:
                print(f"Error registering event handlers for new session: {e}")
        
        # Also register events for Spotify session separately if available and not the current session
        if spotify_session and (not new_session or 
                              (new_session and "spotify" not in str(getattr(new_session, 'source_app_user_model_id', '')).lower())):
            try:
                print("Registering separate event handlers for Spotify session")
                
                # Create a special handler for Spotify
                def spotify_properties_changed(s, a):
                    print("Spotify properties changed while not being the current session")
                    handle_async_callback(spotify_session_changed_handler(s, a))
                
                token = spotify_session.add_media_properties_changed(spotify_properties_changed)
                registered_event_tokens.setdefault("spotify_session", {})["media_properties_changed"] = token
                
                token = spotify_session.add_playback_info_changed(
                    lambda s, a: handle_async_callback(spotify_session_changed_handler(s, a))
                )
                registered_event_tokens.setdefault("spotify_session", {})["playback_info_changed"] = token
                
                registered_event_tokens.setdefault("spotify_session", {})["session_obj"] = spotify_session
            except Exception as e:
                print(f"Error registering event handlers for Spotify session: {e}")
    
    except Exception as e:
        print(f"Error in sessions_changed_handler: {e}")
    
    # Update the current media info
    await update_media_info(force_update=True)


async def media_properties_changed_handler(session, args):
    """
    Handler for when media properties change.
    
    Args:
        session: The media session instance.
        args: Event arguments.
    """
    try:
        app_id = str(session.source_app_user_model_id)
    except:
        app_id = "Unknown"
    
    print(f"Media properties changed for {app_id}")
    await update_media_info(force_update=True)


async def spotify_session_changed_handler(session, args):
    """
    Special handler for Spotify session changes when Spotify is not the current active session.
    This helps the application recover when Spotify is restarted or when it loses focus.
    
    Args:
        session: The Spotify media session.
        args: Event arguments.
    """
    print(f"Spotify session changed while not being the current active session")
    
    # Check if the Spotify session has meaningful content
    try:
        properties = await session.try_get_media_properties_async()
        if properties and properties.title:
            print(f"Spotify playing: {properties.title} by {properties.artist}")
            
            # Force manager to reconsider Spotify as the active session
            manager = await get_media_manager()
            if manager:
                # This will trigger the sessions_changed_handler
                # and properly update if Spotify should be the focus
                await sessions_changed_handler(manager, None)
            else:
                # Direct update if we can't get the manager
                await update_media_info(force_update=True)
    except Exception as e:
        print(f"Error handling Spotify session change: {e}")


async def playback_info_changed_handler(session, args):
    """
    Handler for when playback status changes.
    
    Args:
        session: The media session instance.
        args: Event arguments.
    """
    print(f"Playback info changed for {session.source_app_user_model_id}")
    await update_media_info(force_update=True)


async def timeline_properties_changed_handler(session, args):
    """
    Handler for when timeline properties change.
    
    Args:
        session: The media session instance.
        args: Event arguments.
    """
    print(f"Timeline properties changed for {session.source_app_user_model_id}")
    # This typically updates frequently (for every second of playback)
    # so we don't force a full info update unless it's critical
    await update_media_info(force_update=False, timeline_only=True)


async def update_media_info(force_update=False, timeline_only=False):
    """
    Update the current media information and notify callbacks if there's a change.
    
    Args:
        force_update: If True, always notify callbacks even if info hasn't changed.
        timeline_only: If True, only update timeline-related information.
    """
    global current_media_info
    
    try:
        # For timeline-only updates, we don't need to fetch all properties
        if timeline_only and current_media_info:
            manager = await get_media_manager()
            session = get_current_session(manager)
            
            if session:
                timeline_info = get_timeline_info(session)
                
                if timeline_info:
                    # Update just the timeline properties
                    current_media_info.current_time_seconds = timeline_info.get("current_position_seconds", 0.0)
                    current_media_info.duration_seconds = timeline_info.get("total_duration_seconds", 0.0)
                    current_media_info.timestamp = time.time()
                    
                    # Notify timeline update callbacks
                    for callback in timeline_update_callbacks:
                        try:
                            callback(current_media_info)
                        except Exception as e:
                            print(f"Error in timeline update callback: {e}")
                    
                    return
            else:
                # No active session, create an empty media info to signal nothing is playing
                if current_media_info:
                    print("No active media session, clearing current media info")
                    # Create an empty MediaInfo object with STOPPED status
                    empty_info = MediaInfo(
                        title="",
                        artist="",
                        app_name=current_media_info.app_name,
                        status="STOPPED"
                    )
                    
                    current_media_info = empty_info
                    
                    # Notify callbacks of the change
                    for callback in media_change_callbacks:
                        try:
                            callback(empty_info)
                        except Exception as e:
                            print(f"Error in media change callback (clearing): {e}")
                    return
        
        # Get complete media info
        new_media_info = await get_current_media_info()
        
        # Determine if media has changed significantly
        media_changed = False
        
        if new_media_info:
            # Check if it's a meaningful media state (not just OPENED without content)
            is_meaningful = (new_media_info.title and 
                          new_media_info.title.strip() != '' and 
                          new_media_info.status not in ['OPENED', 'CLOSED', 'STOPPED'] or
                          (new_media_info.status == 'PLAYING' or new_media_info.status == 'PAUSED'))
            
            if not is_meaningful:
                print(f"Detected non-meaningful media state: {new_media_info.app_name} - " +
                      f"\"{new_media_info.title}\" - {new_media_info.status}")
                
                # Create an empty MediaInfo object with STOPPED status for the same app
                empty_info = MediaInfo(
                    title="",
                    artist="",
                    app_name=new_media_info.app_name,
                    status="STOPPED"
                )
                
                # If we previously had meaningful content, consider this a change
                if current_media_info and current_media_info.title and current_media_info.status in ['PLAYING', 'PAUSED']:
                    print(f"Media stopped: {current_media_info.app_name} - {current_media_info.title}")
                    current_media_info = empty_info
                    
                    # Notify callbacks of media stopping
                    for callback in media_change_callbacks:
                        try:
                            callback(empty_info)
                        except Exception as e:
                            print(f"Error in media change callback (non-meaningful): {e}")
                return
            
            # Valid media - check if it changed
            if not current_media_info:
                media_changed = True
            elif (new_media_info.title != current_media_info.title or
                  new_media_info.artist != current_media_info.artist or
                  new_media_info.app_name != current_media_info.app_name or
                  new_media_info.status != current_media_info.status):
                media_changed = True
                
                # Print debug info for significant changes
                print(f"Media changed: {new_media_info.app_name} - {new_media_info.title} - {new_media_info.status}")
                if current_media_info and new_media_info.status != current_media_info.status:
                    print(f"Status changed: {current_media_info.status} -> {new_media_info.status}")
        elif current_media_info:
            # Media was playing but now it's not
            print("No media info available, clearing state")
            
            # Create an empty MediaInfo object with STOPPED status for the same app (if we know it)
            app_name = current_media_info.app_name if current_media_info else "None"
            empty_info = MediaInfo(
                title="",
                artist="",
                app_name=app_name,
                status="STOPPED"
            )
            
            current_media_info = empty_info
            media_changed = True
            
            # Notify callbacks
            for callback in media_change_callbacks:
                try:
                    callback(empty_info)
                except Exception as e:
                    print(f"Error in media change callback (media stopped): {e}")
            return
        
        # Update the current media info
        current_media_info = new_media_info
        
        # Notify callbacks if media has changed or force_update is True
        if (media_changed or force_update) and current_media_info:
            for callback in media_change_callbacks:
                try:
                    callback(current_media_info)
                except Exception as e:
                    print(f"Error in media change callback: {e}")
    
    except Exception as e:
        print(f"Error updating media info: {e}")
        import traceback
        traceback.print_exc()


def register_media_change_callback(callback: Callable[[MediaInfo], None]):
    """
    Register a callback function to be called when media information changes.
    
    Args:
        callback: A function that takes a MediaInfo object as its argument.
    """
    media_change_callbacks.add(callback)


def register_timeline_update_callback(callback: Callable[[MediaInfo], None]):
    """
    Register a callback function to be called when timeline information updates.
    
    Args:
        callback: A function that takes a MediaInfo object as its argument.
    """
    timeline_update_callbacks.add(callback)


def unregister_media_change_callback(callback: Callable[[MediaInfo], None]):
    """
    Unregister a previously registered media change callback.
    
    Args:
        callback: The callback function to unregister.
    """
    media_change_callbacks.discard(callback)


def unregister_timeline_update_callback(callback: Callable[[MediaInfo], None]):
    """
    Unregister a previously registered timeline update callback.
    
    Args:
        callback: The callback function to unregister.
    """
    timeline_update_callbacks.discard(callback)


async def monitor_media_sessions():
    """
    Monitor media sessions and handle events for changes.
    This is the main async function that should be run.
    """
    global registered_event_tokens, monitor_event_loop
    
    try:
        print("Starting media session monitoring...")
        
        # Store the current event loop for use in callbacks
        monitor_event_loop = asyncio.get_running_loop()
        
        # Get the media manager
        manager = await get_media_manager()
        if not manager:
            print("Failed to get media manager. Exiting.")
            return
        
        # Initialize registered_event_tokens dict
        registered_event_tokens = {"manager": {}, "session": {}}
        
        # Register sessions_changed handler
        def sessions_changed_sync_handler(m, a):
            handle_async_callback(sessions_changed_handler(m, a))
        token = manager.add_sessions_changed(sessions_changed_sync_handler)
        registered_event_tokens["manager"]["sessions_changed"] = token
        
        # Get initial session and register its event handlers
        # (this mimics the behavior of the sessions_changed_handler)
        await sessions_changed_handler(manager, None)
        
        # Track the last time we performed a full refresh
        last_refresh_time = time.time()
        
        # Keep the asyncio task running to listen for events
        while True:
            await asyncio.sleep(1)
            
            # Every 30 seconds, perform a full refresh of the media manager and sessions
            # This helps recover from app restarts (especially Spotify)
            current_time = time.time()
            if current_time - last_refresh_time > 30:
                print("Performing periodic media manager refresh...")
                
                try:
                    # Get a fresh media manager instance
                    fresh_manager = await get_media_manager()
                    if fresh_manager:
                        # This will trigger a full refresh of sessions and handlers
                        await sessions_changed_handler(fresh_manager, None)
                    
                    # Force an update of media info
                    await update_media_info(force_update=True)
                except Exception as e:
                    print(f"Error during periodic refresh: {e}")
                
                last_refresh_time = current_time
            
    except Exception as e:
        print(f"Error in monitor_media_sessions: {e}")
    finally:
        # Clean up event handlers
        try:
            # Unregister manager events
            if "manager" in registered_event_tokens and manager:
                for event_name, token in registered_event_tokens["manager"].items():
                    if event_name == "sessions_changed":
                        manager.remove_sessions_changed(token)
                    else:
                        event_remove_method = getattr(manager, f"remove_{event_name}")
                        event_remove_method(token)
            
            # Unregister session events
            if "session" in registered_event_tokens:
                session = registered_event_tokens["session"].get("session_obj")
                if session:
                    for event_name, token in registered_event_tokens["session"].items():
                        if event_name != "session_obj":  # Skip non-token entries
                            try:
                                event_remove_method = getattr(session, f"remove_{event_name}")
                                event_remove_method(token)
                            except Exception as e:
                                print(f"Error unregistering {event_name} handler: {e}")
            
            # Also clean up Spotify session if it exists
            if "spotify_session" in registered_event_tokens:
                session = registered_event_tokens["spotify_session"].get("session_obj")
                if session:
                    for event_name, token in registered_event_tokens["spotify_session"].items():
                        if event_name != "session_obj":  # Skip non-token entries
                            try:
                                event_remove_method = getattr(session, f"remove_{event_name}")
                                event_remove_method(token)
                            except Exception as e:
                                print(f"Error unregistering Spotify {event_name} handler: {e}")
                                
        except Exception as e:
            print(f"Error cleaning up event handlers: {e}")


# Example callback function for testing
def print_media_info(media_info: MediaInfo):
    """
    Print media information to the console.
    """
    print("\n" + "=" * 50)
    print(f"Media changed: {media_info.title}")
    print(f"Artist: {media_info.artist}")
    print(f"Album: {media_info.album_title}")
    print(f"App: {media_info.app_name}")
    print(f"Status: {media_info.status}")
    print(f"Position: {media_info.current_time_seconds:.2f}s / {media_info.duration_seconds:.2f}s")
    print("=" * 50 + "\n")


# For testing purposes - run when the script is executed directly
if __name__ == "__main__":
    try:
        # Register the example callback
        register_media_change_callback(print_media_info)
        
        # Run the monitor
        print("Starting media monitor... Press Ctrl+C to exit.")
        asyncio.run(monitor_media_sessions())
    except KeyboardInterrupt:
        print("\nStopping media monitor...")
    except Exception as e:
        print(f"Error: {e}")