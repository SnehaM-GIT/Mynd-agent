import datetime
import os
import re
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Configurable timezone — defaults to Asia/Kolkata (IST)
CALENDAR_TIMEZONE = os.getenv("MYND_TIMEZONE", "Asia/Kolkata")
CALENDAR_UTC_OFFSET = os.getenv("MYND_UTC_OFFSET", "+05:30")


def get_token_path(user_id):
    """
    Each user gets their own token file inside the tokens/ folder.
    user_id is their unique Chainlit session ID.
    This means User A and User B never share a Google account.
    Example: tokens/token_abc123.json
    """
    os.makedirs("tokens", exist_ok=True)
    return f"tokens/token_{user_id}.json"


def get_calendar_service(user_id):
    """
    Connects to Google Calendar for a specific user.
    Loads their personal token file if it exists.
    Opens browser login if no token exists yet.
    After login, saves token so user is not asked again.
    """
    creds = None
    token_path = get_token_path(user_id)

    # Load this specific user's saved token if it exists
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # If no valid credentials available, ask user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # Token expired but can be refreshed silently
            creds.refresh(Request())
        else:
            # No token at all — open browser for Google login
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save this specific user's token for next time
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    return service


def clear_user_token(user_id):
    """
    Deletes ONLY the login token for this user.
    This forces a fresh Google login next time.
    IMPORTANT: This does NOT touch or delete any calendar events.
    Events live on Google's servers and are completely unaffected.
    This is purely a credential reset — like logging out and back in.
    """
    token_path = get_token_path(user_id)
    if os.path.exists(token_path):
        os.remove(token_path)
        return True
    return False


def resolve_date(date_input):
    """
    Converts ANY date format the user types into YYYY-MM-DD.

    Handles:
    - Relative: today, tomorrow, day after tomorrow
    - Day names: monday, thursday, next friday
    - Written: 15 april, april 15, 15th april
    - Numeric: 15/04, 15-04-2026, 15.04.2026
    - Just a number: 15 means 15th of current month
    - If year missing, assumes current year
    """
    today = datetime.date.today()
    current_year = today.year
    text = date_input.strip().lower()

    # Simple relative words
    if text == "today":
        return today.strftime("%Y-%m-%d")
    if text == "tomorrow":
        return (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    if text in ["day after tomorrow", "day after"]:
        return (today + datetime.timedelta(days=2)).strftime("%Y-%m-%d")

    # Day names like "monday", "next thursday"
    day_names = ["monday", "tuesday", "wednesday", "thursday",
                 "friday", "saturday", "sunday"]
    for i, day in enumerate(day_names):
        if day in text:
            days_ahead = i - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            target = today + datetime.timedelta(days=days_ahead)
            return target.strftime("%Y-%m-%d")

    # Month names written out — full and abbreviated
    month_map = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9,
        "oct": 10, "nov": 11, "dec": 12
    }

    # Try "15 april", "april 15", "15th april" formats
    for month_name, month_num in month_map.items():
        if month_name in text:
            numbers = re.findall(r'\d+', text)
            if numbers:
                day_num = int(numbers[0])
                year_num = int(numbers[1]) if len(numbers) > 1 else current_year
                try:
                    result = datetime.date(year_num, month_num, day_num)
                    return result.strftime("%Y-%m-%d")
                except Exception:
                    pass

    # Numeric formats DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY or DD/MM
    numeric_patterns = [
        r'(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{4})',
        r'(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})',
        r'(\d{1,2})[\/\-\.](\d{1,2})',
    ]
    for pattern in numeric_patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            if len(groups) == 3 and len(groups[0]) == 4:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            elif len(groups) == 3:
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
            else:
                day, month, year = int(groups[0]), int(groups[1]), current_year
            try:
                result = datetime.date(year, month, day)
                return result.strftime("%Y-%m-%d")
            except Exception:
                pass

    # Just a number like "15" — assume 15th of current month
    if text.isdigit():
        day_num = int(text)
        try:
            result = datetime.date(current_year, today.month, day_num)
            return result.strftime("%Y-%m-%d")
        except Exception:
            pass

    # Fallback to today if nothing matched
    return today.strftime("%Y-%m-%d")


def resolve_time(time_input):
    """
    Converts any time format to HH:MM in 24 hour format.

    Handles:
    - 7pm, 7 pm, 7:30pm, 7:30 pm
    - 19:00, 19:30
    - noon, midnight, morning, afternoon, evening, night
    """
    text = time_input.strip().lower()

    # Named times
    if text in ["noon", "12pm", "12 pm"]:
        return "12:00"
    if text in ["midnight", "12am", "12 am"]:
        return "00:00"
    if text in ["morning", "early morning"]:
        return "09:00"
    if text in ["afternoon", "midday"]:
        return "14:00"
    if text in ["evening", "late afternoon"]:
        return "18:00"
    if text in ["night", "tonight"]:
        return "20:00"

    # Handle "7pm", "7:30pm", "7 pm", "7:30 pm"
    match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        period = match.group(3)
        if period == "pm" and hour != 12:
            hour += 12
        if period == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"

    # 24hr format "19:00" or "19:30"
    match = re.search(r'(\d{1,2}):(\d{2})', text)
    if match:
        return f"{int(match.group(1)):02d}:{match.group(2)}"

    # Just a number like "19" — treat as hour in 24hr
    if text.isdigit():
        return f"{int(text):02d}:00"

    # Default to 9am if nothing matched
    return "09:00"


def resolve_duration(duration_input):
    """
    Converts natural language duration to minutes.

    Handles:
    - "quick call", "quick chat" = 15 minutes
    - "brief", "short" = 30 minutes
    - "half hour", "30 min" = 30 minutes
    - "1 hour", "2 hours", "1hr" = 60, 120 minutes
    - Default = 60 minutes
    """
    text = str(duration_input).strip().lower()

    # Quick / brief signals — short meeting
    if any(word in text for word in ["quick", "brief", "short", "fast"]):
        return 30

    # Explicit minute values
    minute_match = re.search(r'(\d+)\s*min', text)
    if minute_match:
        return int(minute_match.group(1))

    # Half hour
    if "half" in text or "30" in text:
        return 30

    # Hour values — "1 hour", "2hrs", "1.5 hour"
    hour_match = re.search(r'(\d+\.?\d*)\s*h', text)
    if hour_match:
        return int(float(hour_match.group(1)) * 60)

    # If it's just a plain number assume hours
    if text.isdigit():
        return int(text) * 60

    # Default to 60 minutes
    return 60


def check_conflicts(user_id, date_input, time_input, duration_minutes=60):
    """
    Checks if any event already exists in the requested time slot.
    Returns list of conflicting events or empty list if slot is free.
    Used before creating an event to warn the user about overlaps.
    """
    service = get_calendar_service(user_id)

    date_str = resolve_date(date_input)
    time_str = resolve_time(time_input)

    # Calculate start and end of the requested slot
    start_datetime = datetime.datetime.fromisoformat(
        f"{date_str}T{time_str}:00"
    )
    end_datetime = start_datetime + datetime.timedelta(minutes=duration_minutes)

    # Ask Google for any events overlapping this window
    events_result = service.events().list(
        calendarId="primary",
        timeMin=start_datetime.isoformat() + CALENDAR_UTC_OFFSET,
        timeMax=end_datetime.isoformat() + CALENDAR_UTC_OFFSET,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    return events_result.get("items", [])


def get_events(user_id, date_input):
    """
    Fetches and returns all events for a specific day.
    Used when user asks what they have scheduled on a day.
    Returns a formatted string with all events and their times.
    """
    service = get_calendar_service(user_id)
    date_str = resolve_date(date_input)

    # Search full day from midnight to midnight
    time_min = f"{date_str}T00:00:00{CALENDAR_UTC_OFFSET}"
    time_max = f"{date_str}T23:59:59{CALENDAR_UTC_OFFSET}"

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = events_result.get("items", [])
    readable = datetime.date.fromisoformat(date_str).strftime("%A, %d %B %Y")

    # No events found that day
    if not events:
        return f"📅 No events on {readable}. Your schedule is clear!"

    # Build formatted list of events with times
    output = f"📅 **Your schedule for {readable}:**\n\n"
    for event in events:
        title = event.get("summary", "Untitled")
        start = event["start"].get("dateTime", "")
        if start:
            time_obj = datetime.datetime.fromisoformat(start)
            time_str = time_obj.strftime("%I:%M %p")
        else:
            time_str = "All day"
        output += f"⏰ {time_str} — {title}\n"

    return output


def create_calendar_event(user_id, title, date_input, time_input,
                           duration_minutes=60, reminder_minutes=30,
                           recurrence=None):
    """
    Creates a Google Calendar event for a specific user.
    user_id ensures the event goes into the correct Google account.
    Accepts any date and time format — resolves them automatically.

    recurrence — optional dict with keys:
        frequency: "daily" | "weekly" | "monthly"
        count: number of times to repeat (e.g. 10)
        until: end date as YYYY-MM-DD string (e.g. "2026-12-31")
    """
    # Use this user's specific Google account
    service = get_calendar_service(user_id)

    # Resolve human readable date and time to standard formats
    date_str = resolve_date(date_input)
    time_str = resolve_time(time_input)

    start_datetime = f"{date_str}T{time_str}:00"
    start = datetime.datetime.fromisoformat(start_datetime)
    end = start + datetime.timedelta(minutes=duration_minutes)
    end_datetime = end.isoformat()

    event = {
        "summary": title,
        "start": {
            "dateTime": start_datetime,
            "timeZone": CALENDAR_TIMEZONE,
        },
        "end": {
            "dateTime": end_datetime,
            "timeZone": CALENDAR_TIMEZONE,
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                # Popup notification on screen
                {"method": "popup", "minutes": reminder_minutes},
                # Email notification as backup
                {"method": "email", "minutes": reminder_minutes},
            ],
        },
    }

    # Add recurrence rule if this is a recurring event
    if recurrence:
        freq_map = {
            "daily": "DAILY",
            "weekly": "WEEKLY",
            "monthly": "MONTHLY"
        }
        freq = freq_map.get(recurrence.get("frequency", "weekly"), "WEEKLY")
        rrule = f"RRULE:FREQ={freq}"

        # Repeat N times
        if recurrence.get("count"):
            rrule += f";COUNT={recurrence['count']}"
        # Repeat until a date
        elif recurrence.get("until"):
            until_date = recurrence["until"].replace("-", "")
            rrule += f";UNTIL={until_date}T235959Z"

        event["recurrence"] = [rrule]

    # Send to Google Calendar API
    created_event = service.events().insert(
        calendarId="primary",
        body=event
    ).execute()

    # Build human readable confirmation message
    readable_date = start.strftime("%A, %d %B %Y")
    readable_time = start.strftime("%I:%M %p")
    duration_text = (
        f"{duration_minutes} minutes"
        if duration_minutes < 60
        else f"{duration_minutes // 60} hour(s)"
    )

    # Add recurrence info to confirmation if applicable
    recurrence_text = ""
    if recurrence:
        freq = recurrence.get("frequency", "weekly")
        if recurrence.get("count"):
            recurrence_text = f"\n🔁 Repeats {freq} for {recurrence['count']} occurrences"
        elif recurrence.get("until"):
            recurrence_text = f"\n🔁 Repeats {freq} until {recurrence['until']}"
        else:
            recurrence_text = f"\n🔁 Repeats {freq}"

    return (
        f"✅ Event created successfully!\n\n"
        f"📌 {title}\n"
        f"🗓 {readable_date}\n"
        f"⏰ {readable_time}\n"
        f"⏱ Duration: {duration_text}\n"
        f"🔔 Reminder: {reminder_minutes} minutes before"
        f"{recurrence_text}"
    )


def create_all_day_calendar_event(user_id, title, date_input, reminder_minutes=24 * 60):
    """
    Creates an all-day Google Calendar event.
    Useful for birthdays, anniversaries, deadlines, holidays, and day blocks.
    """
    service = get_calendar_service(user_id)
    date_str = resolve_date(date_input)
    start_date = datetime.date.fromisoformat(date_str)
    end_date = start_date + datetime.timedelta(days=1)

    event = {
        "summary": title,
        "start": {"date": start_date.isoformat()},
        "end": {"date": end_date.isoformat()},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": reminder_minutes},
                {"method": "email", "minutes": reminder_minutes},
            ],
        },
    }

    service.events().insert(calendarId="primary", body=event).execute()
    readable_date = start_date.strftime("%A, %d %B %Y")
    return (
        "All-day Google Calendar event created successfully.\n\n"
        f"{title}\n"
        f"{readable_date}\n"
        f"Reminder: {reminder_minutes // 60} hour(s) before"
    )


def delete_calendar_event(user_id, title_keyword, date_input):
    """
    Finds and deletes a calendar event by searching for a title keyword
    on a specific date in the user's Google Calendar.
    Only affects events — never affects login or other data.
    """
    # Use this user's specific Google account
    service = get_calendar_service(user_id)

    # Resolve the date to standard format
    date_str = resolve_date(date_input)

    # Search the full day from midnight to midnight
    time_min = f"{date_str}T00:00:00{CALENDAR_UTC_OFFSET}"
    time_max = f"{date_str}T23:59:59{CALENDAR_UTC_OFFSET}"

    # Fetch all events on that day from Google Calendar
    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = events_result.get("items", [])
    readable = datetime.date.fromisoformat(date_str).strftime("%A, %d %B %Y")

    # No events at all on that day
    if not events:
        return f"❌ No events found on {readable}. Nothing was deleted."

    # Search for event matching the title keyword — case insensitive
    matched_event = None
    for event in events:
        event_title = event.get("summary", "").lower()
        if title_keyword.lower() in event_title:
            matched_event = event
            break

    # No matching title found — show what events exist that day
    if not matched_event:
        event_list = "\n".join(
            [f"- {e.get('summary', 'Untitled')}" for e in events]
        )
        return (
            f"❌ Couldn't find '{title_keyword}' on {readable}.\n\n"
            f"Events I found on that day:\n{event_list}\n\n"
            f"Which one did you want to delete?"
        )

    # Delete the matched event from Google Calendar
    service.events().delete(
        calendarId="primary",
        eventId=matched_event["id"]
    ).execute()

    return (
        f"🗑️ Event deleted successfully!\n\n"
        f"📌 {matched_event.get('summary', 'Event')}\n"
        f"🗓 {readable}\n\n"
        f"Your other calendar events are untouched."
    )
