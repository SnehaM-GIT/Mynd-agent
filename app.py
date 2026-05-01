import chainlit as cl  # creates the chat website UI
from groq import Groq  # library to talk to Groq API and Llama model
import os              # operating system — reads .env variables
import datetime
import json
from dotenv import load_dotenv
from calendar_tool import (
    create_calendar_event,
    delete_calendar_event,
    check_conflicts,
    get_events,
    clear_user_token,
    resolve_duration
)

load_dotenv()

# Connect to Groq using the API key stored in .env
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# File to persist conversation history across restarts
# Each user gets their own history file — named by session ID
HISTORY_DIR = "histories"
os.makedirs(HISTORY_DIR, exist_ok=True)

today = datetime.date.today()

SYSTEM_PROMPT = f"""You are Mynd, an AI agent for entrepreneurs.
You help with calendar management, networking, and daily tasks.
You remember everything told to you in this conversation.
Today's date is {today.strftime("%A, %d %B %Y")}.

When a user wants to CREATE, SCHEDULE, BLOCK, SET, or ADD a calendar
event, meeting, reminder, or call — reply ONLY with this exact JSON:

{{"action": "create_event", "title": "event name", "date": "as user said", "time": "as user said or empty string if not mentioned", "duration": "as user said or 1 hour if not mentioned", "reminder": 30, "recurrence": null}}

For RECURRING events like "every monday", "every week", "daily standup",
"every month" — include recurrence like this:

{{"action": "create_event", "title": "event name", "date": "as user said", "time": "as user said", "duration": "1 hour", "reminder": 30, "recurrence": {{"frequency": "weekly", "count": 10}}}}

recurrence frequency must be: "daily", "weekly", or "monthly"
recurrence count = number of times to repeat, default 10 if not specified
recurrence until = end date as YYYY-MM-DD if user specifies an end date

When a user wants to DELETE, REMOVE, CANCEL, CLEAR, DROP,
CALL OFF, or says a meeting IS CANCELLED, WON'T HAPPEN,
IS CALLED OFF, NOT HAPPENING — reply ONLY with this JSON:

{{"action": "delete_event", "title": "event keyword", "date": "as user said"}}

When a user wants to VIEW, SEE, CHECK, SHOW, LIST, or asks
WHAT DO I HAVE or WHAT IS ON MY CALENDAR for a specific day
— reply ONLY with this JSON:

{{"action": "view_events", "date": "as user said"}}

Rules that always apply:
- date: copy exactly what user said e.g. "tomorrow", "friday", "25 april"
- time: copy exactly what user said — use empty string if not mentioned
- duration: copy what user said e.g. "quick call", "30 min", "2 hours"
- reminder: minutes as integer, default 30 if not mentioned
- Output ONLY the JSON for calendar actions. No explanation. Nothing else.

If the user is just chatting and NOT asking for a calendar action,
reply normally as a helpful friendly assistant.
Do NOT output JSON for normal conversation.
"""


def get_history_path(user_id):
    """
    Returns the file path for storing this user's conversation history.
    History is saved to disk so it persists across app restarts.
    Each user gets their own file: histories/history_abc123.json
    """
    return f"{HISTORY_DIR}/history_{user_id}.json"


def load_history(user_id):
    """
    Loads conversation history from disk for this user.
    Returns empty list if no history file exists yet.
    This means memory survives app restarts.
    """
    path = get_history_path(user_id)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []


def save_history(user_id, history):
    """
    Saves conversation history to disk for this user.
    Called after every message so nothing is lost on restart.
    """
    path = get_history_path(user_id)
    with open(path, "w") as f:
        json.dump(history, f)


@cl.on_chat_start
async def start():
    # Each Chainlit session has a unique ID — use as user identifier
    # This ensures each person's token and history are stored separately
    session_id = cl.user_session.get("id")
    user_id = str(session_id)
    cl.user_session.set("user_id", user_id)

    # Load this user's history from disk — survives restarts
    history = load_history(user_id)
    cl.user_session.set("history", history)

    # Greet returning users differently from new users
    if history:
        greeting = (
            "Welcome back! I'm **Mynd** 🚀\n\n"
            "I remember our previous conversations. "
            "How can I help you today?"
        )
    else:
        greeting = (
            "Hi! I'm **Mynd**, your entrepreneur assistant 🚀\n\n"
            "I manage your Google Calendar — create, view, and delete "
            "events using natural language.\n\n"
            "Try saying:\n"
            "- *Block thursday 7pm for Nasscom meetup*\n"
            "- *Every monday 9am team standup*\n"
            "- *What do I have on friday?*\n"
            "- *Cancel my meeting tomorrow with Sowmya*\n\n"
            "Type `/switchaccount` to connect a different Google account.\n"
            "Type `/clearhistory` to reset our conversation memory."
        )

    await cl.Message(content=greeting).send()


@cl.on_message
async def main(message: cl.Message):

    # Get this user's conversation history and unique ID
    history = cl.user_session.get("history")
    user_id = cl.user_session.get("user_id")

    # Safety checks — reset if something went wrong
    if history is None:
        history = []
    if user_id is None:
        user_id = "default"

    # ── COMMAND: /switchaccount ───────────────────────────────────
    # Deletes login token only — calendar events are completely safe
    if message.content.strip().lower() == "/switchaccount":
        was_connected = clear_user_token(user_id)
        if was_connected:
            await cl.Message(
                content="✅ Google account disconnected successfully.\n\n"
                        "📅 All your calendar events are safe — "
                        "switching only affects login, never your data.\n\n"
                        "Next calendar action will ask you to log in again."
            ).send()
        else:
            await cl.Message(
                content="ℹ️ No Google account connected yet.\n\n"
                        "Just create or delete an event and "
                        "you'll be prompted to log in."
            ).send()
        return

    # ── COMMAND: /clearhistory ────────────────────────────────────
    # Wipes conversation memory for this user — fresh start
    if message.content.strip().lower() == "/clearhistory":
        history = []
        cl.user_session.set("history", [])
        save_history(user_id, [])
        await cl.Message(
            content="🧹 Conversation history cleared.\n\n"
                    "I've forgotten our previous chats. "
                    "Your calendar events are untouched."
        ).send()
        return

    # ── HANDLE DELETION CONFIRMATION ─────────────────────────────
    # User previously asked to delete — waiting for YES or NO
    if cl.user_session.get("awaiting_delete_confirm"):
        if message.content.strip().upper() == "YES":
            cl.user_session.set("awaiting_delete_confirm", False)
            pending = cl.user_session.get("pending_delete")
            try:
                # Execute the deletion that was pending confirmation
                result = delete_calendar_event(
                    user_id=user_id,
                    title_keyword=pending["title"],
                    date_input=pending["date"]
                )
                await cl.Message(content=result).send()
            except Exception as e:
                await cl.Message(
                    content=f"Error deleting event: {str(e)}"
                ).send()
        else:
            # User said NO or anything other than YES — cancel deletion
            cl.user_session.set("awaiting_delete_confirm", False)
            await cl.Message(
                content="Deletion cancelled. Your event is safe. ✅"
            ).send()
        return

    # ── HANDLE CONFLICT CONFIRMATION ─────────────────────────────
    # User has a conflict — waiting for YES to force create or NO to cancel
    if cl.user_session.get("awaiting_conflict_confirm"):
        if message.content.strip().upper() == "YES":
            cl.user_session.set("awaiting_conflict_confirm", False)
            pending = cl.user_session.get("pending_event")
            try:
                # Force create even though there is a conflict
                duration_minutes = resolve_duration(
                    str(pending.get("duration", "1 hour"))
                )
                result = create_calendar_event(
                    user_id=user_id,
                    title=pending["title"],
                    date_input=pending["date"],
                    time_input=pending["time"],
                    duration_minutes=duration_minutes,
                    reminder_minutes=int(pending.get("reminder", 30)),
                    recurrence=pending.get("recurrence")
                )
                await cl.Message(content=result).send()
            except Exception as e:
                await cl.Message(
                    content=f"Error creating event: {str(e)}"
                ).send()
        else:
            # User said NO — cancel creation
            cl.user_session.set("awaiting_conflict_confirm", False)
            await cl.Message(
                content="Got it — event not created. "
                        "Give me a different time and I'll try again."
            ).send()
        return

    # ── NORMAL MESSAGE FLOW ───────────────────────────────────────

    # Add the new user message to conversation history
    history.append({
        "role": "user",
        "content": message.content
    })

    # Build full message list — system prompt first then entire history
    # Groq needs the full history every time — it has no memory of its own
    full_messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ] + history

    # Send to Groq — Llama 3.3 70B does the understanding
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=500,
        messages=full_messages
    )

    # Get the reply text from Groq
    reply = response.choices[0].message.content.strip()

    # Try to find and parse JSON in the reply
    # We search for { and } rather than checking specific strings
    # This handles any spacing or formatting Groq uses
    event_data = None
    try:
        json_start = reply.find("{")
        json_end = reply.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            json_str = reply[json_start:json_end]
            parsed = json.loads(json_str)
            # Only treat as calendar action if action field is present
            if parsed.get("action") in [
                "create_event", "delete_event", "view_events"
            ]:
                event_data = parsed
    except json.JSONDecodeError:
        # Not JSON — treat as normal conversation reply
        pass

    if event_data:

        action = event_data.get("action")

        # ── CREATE EVENT ──────────────────────────────────────────
        if action == "create_event":

            # If user didn't mention a time, ask before creating
            if not event_data.get("time") or event_data.get("time").strip() == "":
                # Save partial event so we can complete it after user replies
                cl.user_session.set("pending_event", event_data)
                reply = (
                    f"Got it! I have your event **{event_data['title']}** "
                    f"on **{event_data['date']}**.\n\n"
                    f"What time should I schedule it for?"
                )
                history.append({"role": "assistant", "content": reply})
                cl.user_session.set("history", history)
                save_history(user_id, history)
                await cl.Message(content=reply).send()
                return

            # Resolve duration from natural language to minutes
            # e.g. "quick call" = 30 min, "2 hours" = 120 min
            duration_minutes = resolve_duration(
                str(event_data.get("duration", "1 hour"))
            )

            # Check for conflicts before creating the event
            conflicts = check_conflicts(
                user_id=user_id,
                date_input=event_data["date"],
                time_input=event_data["time"],
                duration_minutes=duration_minutes
            )

            if conflicts:
                # Warn user about existing events in this slot
                conflict_list = "\n".join(
                    [f"- {e.get('summary', 'Untitled')}" for e in conflicts]
                )
                # Save pending event in case user confirms
                cl.user_session.set("pending_event", event_data)
                cl.user_session.set("awaiting_conflict_confirm", True)
                reply = (
                    f"⚠️ You already have something at that time:\n\n"
                    f"{conflict_list}\n\n"
                    f"Do you still want to create "
                    f"**{event_data['title']}** at the same time?\n\n"
                    f"Type **YES** to create anyway or **NO** to cancel."
                )
                history.append({"role": "assistant", "content": reply})
                cl.user_session.set("history", history)
                save_history(user_id, history)
                await cl.Message(content=reply).send()
                return

            # Show the user what we understood before creating
            recurrence_info = ""
            if event_data.get("recurrence"):
                freq = event_data["recurrence"].get("frequency", "weekly")
                recurrence_info = f"\n🔁 Recurring: {freq}"

            duration_text = (
                f"{duration_minutes} minutes"
                if duration_minutes < 60
                else f"{duration_minutes // 60} hour(s)"
            )

            await cl.Message(
                content=f"Got it! Creating this event:\n\n"
                        f"📌 **{event_data['title']}**\n"
                        f"📅 Date: {event_data['date']}\n"
                        f"⏰ Time: {event_data['time']}\n"
                        f"⏱ Duration: {duration_text}\n"
                        f"🔔 Reminder: {event_data['reminder']} mins before"
                        f"{recurrence_info}\n\n"
                        f"Creating now..."
            ).send()

            try:
                # Create the event in this user's Google Calendar
                result = create_calendar_event(
                    user_id=user_id,
                    title=event_data["title"],
                    date_input=event_data["date"],
                    time_input=event_data["time"],
                    duration_minutes=duration_minutes,
                    reminder_minutes=int(event_data.get("reminder", 30)),
                    recurrence=event_data.get("recurrence")
                )
                # result is the success message from calendar_tool.py
                reply = result

            except Exception as e:
                # Tell user exactly what went wrong
                reply = (
                    f"I understood the event but ran into an issue: {str(e)}\n\n"
                    f"Make sure credentials.json is in your project folder "
                    f"and Google Calendar setup is complete."
                )

        # ── DELETE EVENT ──────────────────────────────────────────
        elif action == "delete_event":

            # Ask for confirmation before deleting — prevents accidents
            cl.user_session.set("pending_delete", event_data)
            cl.user_session.set("awaiting_delete_confirm", True)
            reply = (
                f"Are you sure you want to delete this event?\n\n"
                f"📌 **{event_data['title']}**\n"
                f"📅 Date: {event_data['date']}\n\n"
                f"Type **YES** to confirm or **NO** to cancel."
            )

        # ── VIEW EVENTS ───────────────────────────────────────────
        elif action == "view_events":
            try:
                # Fetch and display all events for that day
                result = get_events(
                    user_id=user_id,
                    date_input=event_data["date"]
                )
                reply = result
            except Exception as e:
                reply = f"Couldn't fetch your calendar: {str(e)}"

    # Add the final reply to conversation history
    history.append({
        "role": "assistant",
        "content": reply
    })

    # Save updated history to session and disk
    # Saving to disk means memory survives app restarts
    cl.user_session.set("history", history)
    save_history(user_id, history)

    # Display the reply in the chat window
    await cl.Message(content=reply).send()