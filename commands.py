"""
Command Router & Handlers for VaaniAI Direct Commands
Handles YouTube, Google Search, Timer, Weather, Notes, Reminders, Export, Favorites, Calendar
No LLM processing - direct execution only
"""

import re
import sqlite3
import json
import requests
from datetime import datetime, timedelta
from urllib.parse import urlencode
from pathlib import Path

# Google Calendar imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth import default
    from googleapiclient.discovery import build
    HAS_GOOGLE_CALENDAR = True
except ImportError:
    HAS_GOOGLE_CALENDAR = False
    print("⚠️  Google Calendar libraries not installed. Install with: pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client")

# ===== COMMAND DETECTION =====

def detect_command(transcript: str) -> tuple:
    """
    Detect if transcript matches a direct command pattern
    Returns: (is_command: bool, command_type: str, params: dict)
    """
    transcript_lower = transcript.lower().strip()
    
    # YouTube commands
    if any(phrase in transcript_lower for phrase in ["youtube", "search youtube", "play on youtube"]):
        if "youtube" in transcript_lower:
            # Extract query after youtube
            match = re.search(r'youtube\s+(?:for\s+)?(.+)', transcript_lower)
            if match:
                query = match.group(1).strip()
                return (True, "youtube", {"query": query})
            return (True, "youtube", {"query": "default"})
    
    # Google Search commands
    if any(phrase in transcript_lower for phrase in ["google search", "google ", "search for"]):
        match = re.search(r'(?:google\s+search\s+|google\s+|search\s+(?:for\s+)?)(.+)', transcript_lower)
        if match:
            query = match.group(1).strip()
            return (True, "google_search", {"query": query})
        return (True, "google_search", {"query": "default"})
    
    # Timer commands
    if any(phrase in transcript_lower for phrase in ["set timer", "timer for", "timer", "stopwatch"]):
        if "stopwatch" in transcript_lower:
            return (True, "stopwatch", {})
        # Extract duration (e.g., "5 minutes", "30 seconds")
        match = re.search(r'(?:set\s+)?timer\s+(?:for\s+)?(\d+)\s*(minute|second|hour|min|sec|hr)?s?', transcript_lower)
        if match:
            amount = int(match.group(1))
            unit = match.group(2) or "minute"
            return (True, "timer", {"amount": amount, "unit": unit})
        return (True, "timer", {"amount": 5, "unit": "minute"})
    
    # Weather commands
    if any(phrase in transcript_lower for phrase in ["weather", "what's the weather", "tell me weather", "weather forecast"]):
        return (True, "weather", {})
    
    # Notes commands
    if "save note" in transcript_lower or "note:" in transcript_lower:
        # Extract note content
        match = re.search(r'(?:save\s+)?note[\s:]+(.+)', transcript_lower)
        if match:
            note_text = match.group(1).strip()
            return (True, "save_note", {"text": note_text})
        return (True, "save_note", {"text": ""})
    
    if any(phrase in transcript_lower for phrase in ["view notes", "show notes", "list notes"]):
        return (True, "view_notes", {})
    
    # Reminder commands
    if "remind me" in transcript_lower or "set reminder" in transcript_lower:
        # Extract delay and reminder text
        match = re.search(r'(?:remind\s+me\s+(?:in|after)\s+)?(.+?)\s+(?:to|that|:)\s+(.+)', transcript_lower)
        if match:
            delay_str = match.group(1).strip()
            reminder_text = match.group(2).strip()
            return (True, "set_reminder", {"delay": delay_str, "text": reminder_text})
        # Fallback: just text
        match = re.search(r'(?:remind\s+me\s+(?:in|after)\s+)?(\d+)\s*(minute|second|hour)', transcript_lower)
        if match:
            return (True, "set_reminder", {"delay": f"{match.group(1)} {match.group(2)}", "text": "reminder"})
    
    if any(phrase in transcript_lower for phrase in ["view reminders", "show reminders", "list reminders"]):
        return (True, "view_reminders", {})
    
    # Export commands
    if any(phrase in transcript_lower for phrase in ["export conversation", "download chat", "export chat", "save chat"]):
        format_type = "json"  # default
        if "csv" in transcript_lower:
            format_type = "csv"
        elif "txt" in transcript_lower or "text" in transcript_lower:
            format_type = "txt"
        return (True, "export", {"format": format_type})
    
    # Favorite commands
    if any(phrase in transcript_lower for phrase in ["favorite", "pin", "star", "add to favorites", "save this"]):
        return (True, "toggle_favorite", {})
    
    # Calendar commands
    if any(phrase in transcript_lower for phrase in ["schedule", "add event", "create event", "calendar event", "meeting"]):
        return (True, "calendar_event", {"details": transcript})
    
    # Not a direct command
    return (False, None, {})


# ===== COMMAND HANDLERS =====

DB_PATH = Path(__file__).parent / "chats.db"

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def handle_youtube(params: dict) -> dict:
    """Handle YouTube search command"""
    query = params.get("query", "").strip()
    if not query or query == "default":
        url = "https://www.youtube.com"
        text = "Opening YouTube..."
    else:
        encoded_query = urlencode({"search_query": query})
        url = f"https://www.youtube.com/results?{encoded_query}"
        text = f"Searching YouTube for: {query}"
    
    return {
        "type": "youtube",
        "title": "YouTube Search",
        "url": url,
        "text": text,
        "query": query
    }


def handle_google_search(params: dict) -> dict:
    """Handle Google search command"""
    query = params.get("query", "").strip()
    if not query or query == "default":
        url = "https://www.google.com"
        text = "Opening Google..."
    else:
        encoded_query = urlencode({"q": query})
        url = f"https://www.google.com/search?{encoded_query}"
        text = f"Searching Google for: {query}"
    
    return {
        "type": "google_search",
        "title": "Google Search",
        "url": url,
        "text": text,
        "query": query
    }


def handle_timer(params: dict) -> dict:
    """Handle timer command"""
    amount = params.get("amount", 5)
    unit = params.get("unit", "minute").lower()
    
    # Convert to seconds
    unit_map = {"minute": 60, "min": 60, "second": 1, "sec": 1, "hour": 3600, "hr": 3600}
    multiplier = unit_map.get(unit, 60)
    seconds = amount * multiplier
    
    return {
        "type": "timer",
        "title": "Timer",
        "seconds": seconds,
        "display": f"{amount} {unit}{'s' if amount > 1 else ''}",
        "text": f"Timer set for {amount} {unit}{'s' if amount > 1 else ''}"
    }


def handle_stopwatch(params: dict) -> dict:
    """Handle stopwatch command"""
    return {
        "type": "stopwatch",
        "title": "Stopwatch",
        "text": "Stopwatch started"
    }


def handle_weather(params: dict) -> dict:
    """Handle weather command - uses free open-meteo API"""
    try:
        # Default location (can be enhanced with geolocation)
        # Using San Francisco as default
        lat, lon = 37.7749, -122.4194
        
        # Call open-meteo API (free, no key needed)
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m&timezone=auto"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            current = data.get("current", {})
            
            temp = current.get("temperature_2m", "--")
            humidity = current.get("relative_humidity_2m", "--")
            wind_speed = current.get("wind_speed_10m", "--")
            weather_code = current.get("weather_code", 0)
            
            # Weather code interpretation (WMO Weather interpretation codes)
            weather_desc = {
                0: "Clear sky",
                1: "Mainly clear",
                2: "Partly cloudy",
                3: "Overcast",
                45: "Foggy",
                48: "Depositing rime fog",
                51: "Light drizzle",
                53: "Moderate drizzle",
                55: "Dense drizzle",
                61: "Slight rain",
                63: "Moderate rain",
                65: "Heavy rain",
                71: "Slight snow",
                73: "Moderate snow",
                75: "Heavy snow",
                80: "Slight rain showers",
                81: "Moderate rain showers",
                82: "Violent rain showers",
                85: "Slight snow showers",
                86: "Heavy snow showers",
                95: "Thunderstorm",
                96: "Thunderstorm with slight hail",
                99: "Thunderstorm with heavy hail"
            }.get(weather_code, "Unknown")
            
            return {
                "type": "weather",
                "title": "Weather",
                "temperature": temp,
                "condition": weather_desc,
                "humidity": humidity,
                "wind_speed": wind_speed,
                "text": f"Current weather: {temp}°C, {weather_desc}, Humidity: {humidity}%"
            }
    except Exception as e:
        print(f"Weather API error: {e}")
    
    return {
        "type": "weather",
        "title": "Weather",
        "text": "Unable to fetch weather",
        "error": "Weather service temporarily unavailable"
    }


def handle_save_note(params: dict, conversation_id: str) -> dict:
    """Handle save note command"""
    text = params.get("text", "").strip()
    
    if not text:
        return {
            "type": "save_note",
            "title": "Save Note",
            "status": "error",
            "text": "Please provide note content"
        }
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        note_id = str(__import__("uuid").uuid4())
        cursor.execute("""
            INSERT INTO notes (id, conversation_id, content, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (note_id, conversation_id, text))
        
        conn.commit()
        conn.close()
        
        return {
            "type": "save_note",
            "title": "Note Saved",
            "status": "success",
            "text": f"Note saved: {text[:50]}{'...' if len(text) > 50 else ''}"
        }
    except Exception as e:
        return {
            "type": "save_note",
            "title": "Save Note",
            "status": "error",
            "text": f"Error saving note: {str(e)}"
        }


def handle_view_notes(params: dict, conversation_id: str) -> dict:
    """Handle view notes command"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, content, created_at FROM notes
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT 50
        """, (conversation_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        notes_list = [dict(row) for row in rows]
        
        return {
            "type": "view_notes",
            "title": "Saved Notes",
            "notes": notes_list,
            "count": len(notes_list),
            "text": f"You have {len(notes_list)} saved notes"
        }
    except Exception as e:
        return {
            "type": "view_notes",
            "title": "Saved Notes",
            "status": "error",
            "text": f"Error fetching notes: {str(e)}"
        }


def handle_set_reminder(params: dict, conversation_id: str) -> dict:
    """Handle set reminder command"""
    delay_str = params.get("delay", "5 minutes")
    reminder_text = params.get("text", "Reminder").strip()
    
    try:
        # Parse delay string (e.g., "5 minutes", "30 seconds", "2 hours")
        match = re.search(r'(\d+)\s*(minute|second|hour|min|sec|hr)', delay_str.lower())
        if match:
            amount = int(match.group(1))
            unit = match.group(2).lower()
            
            # Convert to seconds
            unit_map = {"minute": 60, "min": 60, "second": 1, "sec": 1, "hour": 3600, "hr": 3600}
            seconds = amount * unit_map.get(unit, 60)
        else:
            seconds = 300  # Default 5 minutes
        
        # Calculate trigger time
        trigger_time = datetime.now() + timedelta(seconds=seconds)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        reminder_id = str(__import__("uuid").uuid4())
        cursor.execute("""
            INSERT INTO reminders (id, conversation_id, content, trigger_time, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (reminder_id, conversation_id, reminder_text, trigger_time.isoformat()))
        
        conn.commit()
        conn.close()
        
        display_time = f"{amount} {unit}{'s' if amount > 1 else ''}"
        
        return {
            "type": "set_reminder",
            "title": "Reminder Set",
            "status": "success",
            "reminder_id": reminder_id,
            "trigger_time": trigger_time.isoformat(),
            "seconds": seconds,
            "text": f"Reminder set: '{reminder_text}' in {display_time}",
            "content": reminder_text
        }
    except Exception as e:
        return {
            "type": "set_reminder",
            "title": "Set Reminder",
            "status": "error",
            "text": f"Error setting reminder: {str(e)}"
        }


def handle_view_reminders(params: dict, conversation_id: str) -> dict:
    """Handle view reminders command"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, content, trigger_time, created_at FROM reminders
            WHERE conversation_id = ? AND completed = 0
            ORDER BY trigger_time ASC
            LIMIT 50
        """, (conversation_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        reminders_list = [dict(row) for row in rows]
        
        return {
            "type": "view_reminders",
            "title": "Active Reminders",
            "reminders": reminders_list,
            "count": len(reminders_list),
            "text": f"You have {len(reminders_list)} active reminders"
        }
    except Exception as e:
        return {
            "type": "view_reminders",
            "title": "Active Reminders",
            "status": "error",
            "text": f"Error fetching reminders: {str(e)}"
        }


def handle_export(params: dict, conversation_id: str, messages: list) -> dict:
    """Handle export conversation command"""
    format_type = params.get("format", "json").lower()
    
    try:
        if format_type == "json":
            export_data = {
                "conversation_id": conversation_id,
                "exported_at": datetime.now().isoformat(),
                "message_count": len(messages),
                "messages": messages
            }
            content = json.dumps(export_data, indent=2, ensure_ascii=False)
            filename = f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            mime_type = "application/json"
        
        elif format_type == "csv":
            lines = ["Timestamp,Role,Content"]
            for msg in messages:
                timestamp = msg.get("timestamp", "")
                role = msg.get("role", "")
                content = msg.get("content", "").replace('"', '""')  # Escape quotes
                lines.append(f'"{timestamp}","{role}","{content}"')
            content = "\n".join(lines)
            filename = f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            mime_type = "text/csv"
        
        else:  # txt
            lines = []
            for msg in messages:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", "")
                lines.append(f"[{timestamp}] {role}:")
                lines.append(content)
                lines.append("")
            content = "\n".join(lines)
            filename = f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            mime_type = "text/plain"
        
        return {
            "type": "export",
            "title": "Export Conversation",
            "status": "success",
            "filename": filename,
            "content": content,
            "mime_type": mime_type,
            "format": format_type,
            "text": f"Conversation exported as {format_type.upper()}"
        }
    except Exception as e:
        return {
            "type": "export",
            "title": "Export Conversation",
            "status": "error",
            "text": f"Error exporting conversation: {str(e)}"
        }


def handle_toggle_favorite(params: dict, conversation_id: str, current_is_favorite: bool) -> dict:
    """Handle toggle favorite command"""
    try:
        new_state = not current_is_favorite
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE conversations SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (int(new_state), conversation_id))
        conn.commit()
        conn.close()
        
        action = "added to" if new_state else "removed from"
        
        return {
            "type": "toggle_favorite",
            "title": "Toggle Favorite",
            "status": "success",
            "is_favorite": new_state,
            "text": f"Conversation {action} favorites"
        }
    except Exception as e:
        return {
            "type": "toggle_favorite",
            "title": "Toggle Favorite",
            "status": "error",
            "text": f"Error updating favorite: {str(e)}"
        }


def get_google_calendar_service():
    """Get authenticated Google Calendar service using credentials.json"""
    if not HAS_GOOGLE_CALENDAR:
        return None
    
    try:
        creds = None
        creds_path = Path(__file__).parent / "credentials.json"
        token_path = Path(__file__).parent / "token.json"
        
        # If we have a saved token, use it
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), ['https://www.googleapis.com/auth/calendar'])
        
        # If no valid creds, use service account or credentials.json
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif creds_path.exists():
                # Try to build service with credentials.json
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(creds_path),
                    ['https://www.googleapis.com/auth/calendar']
                )
                creds = flow.run_local_server(port=0)
                
                # Save token for next time
                with open(str(token_path), 'w') as token_file:
                    token_file.write(creds.to_json())
        
        if creds:
            return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        print(f"Error getting Google Calendar service: {e}")
    
    return None


def parse_datetime_from_text(text: str):
    """Parse natural language datetime from text"""
    now = datetime.now()
    text_lower = text.lower()
    
    # Date parsing
    if "tomorrow" in text_lower:
        date = now + timedelta(days=1)
    elif "today" in text_lower:
        date = now
    elif "next monday" in text_lower:
        days_ahead = 0 - now.weekday()  # Monday is 0
        if days_ahead <= 0:
            days_ahead += 7
        date = now + timedelta(days=days_ahead)
    elif "next tuesday" in text_lower:
        days_ahead = 1 - now.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        date = now + timedelta(days=days_ahead)
    else:
        date = now
    
    # Time parsing
    time_match = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)?', text_lower)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        ampm = time_match.group(3)
        
        # Convert to 24-hour format
        if ampm == 'pm' and hour != 12:
            hour += 12
        elif ampm == 'am' and hour == 12:
            hour = 0
        
        return datetime(date.year, date.month, date.day, hour, minute)
    
    return datetime(date.year, date.month, date.day, 14, 0)  # Default 2 PM


def handle_calendar_event(params: dict, conversation_id: str) -> dict:
    """Handle calendar event command - create event on Google Calendar"""
    details = params.get("details", "").strip()
    
    try:
        # Extract event details from natural language
        # Look for event title (first few words or until "at")
        title_match = re.match(r'(?:schedule|add|create)?\s*(?:meeting|event|call)?\s*(?:with|to\s+)?(.+?)(?:\s+(?:at|on|tomorrow|today|next))?', details.lower())
        title = title_match.group(1).strip() if title_match else "Event"
        
        # Clean up title
        title = title.replace("meeting", "").replace("event", "").replace("call", "").strip()
        if not title or len(title) < 2:
            title = "Calendar Event"
        
        # Look for date/time
        start_time = parse_datetime_from_text(details)
        end_time = start_time + timedelta(hours=1)  # Default 1 hour duration
        
        # Look for duration
        duration_match = re.search(r'(?:for|duration:?)\s+(\d+)\s*(?:hour|hr|minute|min)?', details.lower())
        if duration_match:
            duration_val = int(duration_match.group(1))
            if 'hour' in details.lower() or 'hr' in details.lower():
                end_time = start_time + timedelta(hours=duration_val)
            else:
                end_time = start_time + timedelta(minutes=duration_val)
        
        # Look for attendees
        attendee_match = re.search(r'(?:with|attendees?:?)\s+([^a-z]+?)(?:\s+(?:at|on|to|for))?', details.lower())
        attendees = attendee_match.group(1).strip() if attendee_match else ""
        attendee_emails = []
        
        # Try to get calendar service
        service = get_google_calendar_service()
        
        if service:
            # Create event
            event = {
                'summary': title[:100],
                'description': details[:500],
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'UTC'
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'UTC'
                }
            }
            
            # Add attendees if provided
            if attendees:
                event['attendees'] = [{'email': attendees.strip() + '@gmail.com'}]
            
            # Insert event into primary calendar
            try:
                result = service.events().insert(calendarId='primary', body=event).execute()
                event_link = result.get('htmlLink', '')
                event_id = result.get('id', '')
                
                return {
                    "type": "calendar_event",
                    "title": "Calendar Event Created",
                    "status": "success",
                    "event": {
                        "title": title,
                        "date": start_time.strftime("%A, %B %d, %Y"),
                        "time": start_time.strftime("%I:%M %p"),
                        "attendees": attendees,
                        "description": details
                    },
                    "calendar_link": event_link,
                    "event_id": event_id,
                    "text": f"✅ Event created: '{title}' on {start_time.strftime('%A at %I:%M %p')}" + (f" with {attendees}" if attendees else "")
                }
            except Exception as e:
                print(f"Calendar API error: {e}")
                # Fallback to preview if API call fails
                date_str = start_time.strftime("%A, %B %d")
                time_str = start_time.strftime("%I:%M %p")
                
                return {
                    "type": "calendar_event",
                    "title": "Calendar Event Preview",
                    "status": "preview",
                    "event": {
                        "title": title,
                        "date": date_str,
                        "time": time_str,
                        "attendees": attendees,
                        "description": details
                    },
                    "text": f"Event preview: '{title}' on {date_str} at {time_str}" + (f" with {attendees}" if attendees else "") + f"\n⚠️ Error: {str(e)}"
                }
        else:
            # Return preview if no service available
            date_str = start_time.strftime("%A, %B %d")
            time_str = start_time.strftime("%I:%M %p")
            
            return {
                "type": "calendar_event",
                "title": "Calendar Event Preview",
                "status": "preview",
                "event": {
                    "title": title,
                    "date": date_str,
                    "time": time_str,
                    "attendees": attendees,
                    "description": details
                },
                "text": f"Event preview: '{title}' on {date_str} at {time_str}" + (f" with {attendees}" if attendees else "") + "\n📝 Google Calendar not connected yet. Provide credentials to enable."
            }
    except Exception as e:
        print(f"Calendar event error: {e}")
        return {
            "type": "calendar_event",
            "title": "Calendar Event",
            "status": "error",
            "text": f"Error creating event: {str(e)}"
        }


# ===== MAIN ROUTER =====

def route_command(transcript: str, conversation_id: str, messages: list = None) -> dict:
    """
    Main command router - detects command and executes handler
    Returns: (is_direct_command: bool, response: dict or None)
    """
    is_command, cmd_type, params = detect_command(transcript)
    
    if not is_command:
        return (False, None)
    
    # Get current favorite status
    current_is_favorite = False
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_favorite FROM conversations WHERE id = ?", (conversation_id,))
        row = cursor.fetchone()
        conn.close()
        current_is_favorite = bool(row["is_favorite"]) if row else False
    except:
        pass
    
    # Route to appropriate handler
    if cmd_type == "youtube":
        response = handle_youtube(params)
    elif cmd_type == "google_search":
        response = handle_google_search(params)
    elif cmd_type == "timer":
        response = handle_timer(params)
    elif cmd_type == "stopwatch":
        response = handle_stopwatch(params)
    elif cmd_type == "weather":
        response = handle_weather(params)
    elif cmd_type == "save_note":
        response = handle_save_note(params, conversation_id)
    elif cmd_type == "view_notes":
        response = handle_view_notes(params, conversation_id)
    elif cmd_type == "set_reminder":
        response = handle_set_reminder(params, conversation_id)
    elif cmd_type == "view_reminders":
        response = handle_view_reminders(params, conversation_id)
    elif cmd_type == "export":
        response = handle_export(params, conversation_id, messages or [])
    elif cmd_type == "toggle_favorite":
        response = handle_toggle_favorite(params, conversation_id, current_is_favorite)
    elif cmd_type == "calendar_event":
        response = handle_calendar_event(params, conversation_id)
    else:
        return (False, None)
    
    return (True, response)
