import datetime
import json
import os

import requests

from calendar_tool import resolve_date, resolve_time


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
AUTHORITY = "https://login.microsoftonline.com/common"
SCOPES = ["Calendars.ReadWrite", "User.Read"]


class MicrosoftCalendarNotConnected(RuntimeError):
    pass


def _import_msal():
    try:
        import msal
    except ImportError as exc:
        raise RuntimeError(
            "Microsoft Calendar support needs the msal package. "
            "Run `pip install -r requirements.txt` after updating dependencies."
        ) from exc
    return msal


def get_microsoft_cache_path(user_id):
    os.makedirs("tokens", exist_ok=True)
    return f"tokens/microsoft_cache_{user_id}.json"


def _get_client_id():
    client_id = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
    if not client_id:
        raise RuntimeError(
            "Microsoft Calendar is not configured yet. Add MICROSOFT_CLIENT_ID "
            "to your .env from an Azure app registration with delegated "
            "Calendars.ReadWrite permission."
        )
    return client_id


def _load_cache(user_id):
    msal = _import_msal()
    cache = msal.SerializableTokenCache()
    path = get_microsoft_cache_path(user_id)
    if os.path.exists(path):
        with open(path, "r") as f:
            cache.deserialize(f.read())
    return cache


def _save_cache(user_id, cache):
    if cache.has_state_changed:
        with open(get_microsoft_cache_path(user_id), "w") as f:
            f.write(cache.serialize())


def _build_app(user_id):
    msal = _import_msal()
    cache = _load_cache(user_id)
    app = msal.PublicClientApplication(
        client_id=_get_client_id(),
        authority=AUTHORITY,
        token_cache=cache,
    )
    return app, cache


def start_microsoft_device_login(user_id):
    app, cache = _build_app(user_id)
    flow = app.initiate_device_flow(scopes=SCOPES)
    _save_cache(user_id, cache)
    if "user_code" not in flow:
        raise RuntimeError(f"Could not start Microsoft login: {flow}")
    return flow


def finish_microsoft_device_login(user_id, flow, timeout=5):
    app, cache = _build_app(user_id)
    result = app.acquire_token_by_device_flow(flow, timeout=timeout)
    _save_cache(user_id, cache)

    if "access_token" in result:
        return True, "Microsoft Calendar connected successfully."

    error = result.get("error", "authorization_pending")
    if error == "authorization_pending":
        return False, "Microsoft login is still pending. Finish login, then type DONE again."

    description = result.get("error_description", error)
    return False, f"Microsoft login failed: {description}"


def clear_microsoft_token(user_id):
    path = get_microsoft_cache_path(user_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def _get_access_token(user_id):
    app, cache = _build_app(user_id)
    accounts = app.get_accounts()
    if not accounts:
        return None
    result = app.acquire_token_silent(SCOPES, account=accounts[0])
    _save_cache(user_id, cache)
    return result.get("access_token") if result else None


def is_microsoft_connected(user_id):
    try:
        return bool(_get_access_token(user_id))
    except Exception:
        return False


def _require_token(user_id):
    token = _get_access_token(user_id)
    if not token:
        raise MicrosoftCalendarNotConnected(
            "Microsoft Calendar is not connected. Run `/microsoftcalendar`, "
            "complete the login, then type DONE."
        )
    return token


def _graph_request(user_id, method, path, **kwargs):
    token = _require_token(user_id)
    headers = kwargs.pop("headers", {})
    headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": 'outlook.timezone="Asia/Kolkata"',
    })
    response = requests.request(
        method,
        f"{GRAPH_BASE_URL}{path}",
        headers=headers,
        timeout=20,
        **kwargs,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"Microsoft Graph error {response.status_code}: {response.text}"
        )
    if response.status_code == 204:
        return {}
    return response.json()


def _event_window(date_input, time_input=None, duration_minutes=60):
    date_str = resolve_date(date_input)
    if time_input is None:
        start = datetime.datetime.fromisoformat(f"{date_str}T00:00:00")
        end = start + datetime.timedelta(days=1)
    else:
        time_str = resolve_time(time_input)
        start = datetime.datetime.fromisoformat(f"{date_str}T{time_str}:00")
        end = start + datetime.timedelta(minutes=duration_minutes)
    return date_str, start, end


def check_microsoft_conflicts(user_id, date_input, time_input, duration_minutes=60):
    _, start, end = _event_window(date_input, time_input, duration_minutes)
    data = _graph_request(
        user_id,
        "GET",
        "/me/calendar/calendarView",
        params={
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$orderby": "start/dateTime",
        },
    )
    return data.get("value", [])


def get_microsoft_events(user_id, date_input):
    date_str, start, end = _event_window(date_input)
    data = _graph_request(
        user_id,
        "GET",
        "/me/calendar/calendarView",
        params={
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$orderby": "start/dateTime",
        },
    )
    events = data.get("value", [])
    readable = datetime.date.fromisoformat(date_str).strftime("%A, %d %B %Y")

    if not events:
        return f"No Microsoft Calendar events on {readable}. Your schedule is clear!"

    output = f"**Your Microsoft Calendar schedule for {readable}:**\n\n"
    for event in events:
        title = event.get("subject", "Untitled")
        start_info = event.get("start", {})
        start_value = start_info.get("dateTime", "")
        if start_value:
            time_obj = datetime.datetime.fromisoformat(start_value)
            time_str = time_obj.strftime("%I:%M %p")
        else:
            time_str = "All day"
        output += f"- {time_str} - {title}\n"

    return output


def create_microsoft_calendar_event(
    user_id,
    title,
    date_input,
    time_input,
    duration_minutes=60,
    reminder_minutes=30,
    recurrence=None,
):
    date_str, start, end = _event_window(date_input, time_input, duration_minutes)
    body = {
        "subject": title,
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "isReminderOn": True,
        "reminderMinutesBeforeStart": reminder_minutes,
    }

    if recurrence:
        freq = recurrence.get("frequency", "weekly").lower()
        interval_map = {
            "daily": "daily",
            "weekly": "weekly",
            "monthly": "absoluteMonthly",
        }
        pattern = {
            "type": interval_map.get(freq, "weekly"),
            "interval": 1,
        }
        if freq == "weekly":
            pattern["daysOfWeek"] = [start.strftime("%A").lower()]
        if freq == "monthly":
            pattern["dayOfMonth"] = start.day

        range_info = {
            "type": "numbered" if recurrence.get("count") else "noEnd",
            "startDate": date_str,
        }
        if recurrence.get("count"):
            range_info["numberOfOccurrences"] = int(recurrence["count"])
        elif recurrence.get("until"):
            range_info = {
                "type": "endDate",
                "startDate": date_str,
                "endDate": resolve_date(recurrence["until"]),
            }

        body["recurrence"] = {
            "pattern": pattern,
            "range": range_info,
        }

    _graph_request(user_id, "POST", "/me/calendar/events", json=body)

    readable_date = start.strftime("%A, %d %B %Y")
    readable_time = start.strftime("%I:%M %p")
    duration_text = (
        f"{duration_minutes} minutes"
        if duration_minutes < 60
        else f"{duration_minutes // 60} hour(s)"
    )
    recurrence_text = ""
    if recurrence:
        recurrence_text = f"\nRepeats {recurrence.get('frequency', 'weekly')}"
        if recurrence.get("count"):
            recurrence_text += f" for {recurrence['count']} occurrences"

    return (
        "Microsoft Calendar event created successfully!\n\n"
        f"{title}\n"
        f"{readable_date}\n"
        f"{readable_time}\n"
        f"Duration: {duration_text}\n"
        f"Reminder: {reminder_minutes} minutes before"
        f"{recurrence_text}"
    )


def delete_microsoft_calendar_event(user_id, title_keyword, date_input):
    date_str, start, end = _event_window(date_input)
    data = _graph_request(
        user_id,
        "GET",
        "/me/calendar/calendarView",
        params={
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat(),
            "$orderby": "start/dateTime",
        },
    )
    events = data.get("value", [])
    readable = datetime.date.fromisoformat(date_str).strftime("%A, %d %B %Y")

    if not events:
        return f"No Microsoft Calendar events found on {readable}. Nothing was deleted."

    matched_event = None
    keyword = title_keyword.lower()
    for event in events:
        if keyword in event.get("subject", "").lower():
            matched_event = event
            break

    if not matched_event:
        event_list = "\n".join(
            [f"- {e.get('subject', 'Untitled')}" for e in events]
        )
        return (
            f"Couldn't find '{title_keyword}' on {readable}.\n\n"
            f"Events I found:\n{event_list}"
        )

    _graph_request(user_id, "DELETE", f"/me/events/{matched_event['id']}")
    return (
        "Microsoft Calendar event deleted successfully!\n\n"
        f"{matched_event.get('subject', 'Event')}\n"
        f"{readable}"
    )
