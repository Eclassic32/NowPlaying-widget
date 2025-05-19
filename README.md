# Windows Media Stream Widget

A web-based widget that displays information about currently playing media on Windows. The application integrates with Windows APIs to access media information and presents it through a local web server.

## Features

- Displays information about currently playing media (song name, artist, album, app name, playback status)
- Shows playback position and duration
- Provides two viewing options:
  - `/currentlyplaying`: A persistent display showing all media information
  - `/nowplaying`: A notification-style display that appears briefly when media changes
- Customizable styling based on the media application (different styles for Spotify, YouTube, etc.)

## Requirements

- Windows 10 or later
- Python 3.9 or higher
- Required Python packages:
  - flask
  - winrt-Windows.Media.Control
  - winrt-Windows.Foundation
  - winrt-runtime

## Installation

1. Clone or download this repository
2. Install the required dependencies:
   ```py
   pip install flask winrt-Windows.Media.Control winrt-Windows.Foundation winrt-runtime
   ```

## Usage

Run the application:
```
python run_app.py
```

Then open a web browser and navigate to:
- `http://localhost:5000/currentlyplaying` - For the full media display
- `http://localhost:5000/nowplaying` - For the notification-style display

## Customization

You can customize the appearance of the widget by modifying the `workspace/static/style.scss` file. The widget uses the `data-app-name` attribute to apply application-specific styling, making it easy to create unique styles for different media applications.

> In case if script or your custom designs doesn't work with `workspace/static/style.scss` you can enable `backup.style.css` by deleting `backup` from file name. 

## Project Structure

- `code/media_manager.py`: Core module that interacts with Windows Media APIs
- `code/app.py`: Flask web server that serves the media information
- `templates/currently_playing.html`: Template for the full display
- `templates/now_playing_notification.html`: Template for the notification display
- `static/style.css`: CSS styling for both displays

## How It Works

1. The application uses the Windows Runtime API through `pywinrt` to access the `GlobalSystemMediaTransportControlsSessionManager`
2. It monitors for media changes using event handlers
3. When media changes are detected, the information is captured and made available through the web server
4. The web interface periodically polls the server for updates and refreshes the display accordingly

## TODO

- [ ] Add more custom CSS for apps.
- [ ] Figure out how to access tab/domain information in browser.
- [ ] Make it so OBS can start script when needed.
- [ ] Make actual player from this thing?