import chainlit as cl  # creates the chat website UI
from groq import Groq  # library to talk to Groq API and Llama model
import os              # operating system — reads .env variables
import datetime
import json
import base64
import re
from dotenv import load_dotenv
from calendar_tool import (
    create_calendar_event,
    delete_calendar_event,
    check_conflicts,
    get_events,
    clear_user_token,
    resolve_duration
)
from networking_tool import (
    add_contact,
    search_contacts,
    get_all_contacts,
    generate_followup_message,
    format_contact_card,
    format_contacts_list,
    mark_message_sent,
    extract_contact_from_text,
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
You help with calendar management, networking follow-ups, and daily tasks.
You remember everything told to you in this conversation.
Today's date is {today.strftime("%A, %d %B %Y")}.

════════════════════════════════════════════
CALENDAR ACTIONS
════════════════════════════════════════════

When a user wants to CREATE, SCHEDULE, BLOCK, SET, or ADD a calendar
event, meeting, reminder, or call — reply ONLY with this exact JSON:

{{"action": "create_event", "title": "event name", "date": "as user said", "time": "as user said or empty string if not mentioned", "duration": "as user said or 1 hour if not mentioned", "reminder": 30, "recurrence": null}}

For RECURRING events like "every monday", "every week", "daily standup",
"every month" — include recurrence like this:

{{"action": "create_event", "title": "event name", "date": "as user said", "time": "as user said", "duration": "1 hour", "reminder": 30, "recurrence": {{"frequency": "weekly", "count": 10}}}}

recurrence frequency must be: "daily", "weekly", or "monthly"

When a user wants to DELETE, REMOVE, or CANCEL an event:
{{"action": "delete_event", "title": "event keyword", "date": "as user said"}}

When a user wants to VIEW their calendar for a day:
{{"action": "view_events", "date": "as user said"}}

════════════════════════════════════════════
NETWORKING ACTIONS
════════════════════════════════════════════

When a user mentions meeting someone, shares a business card, gives
contact details, or says they met someone at an event — extract the
contact and reply ONLY with this JSON:

{{"action": "save_contact", "name": "full name", "role": "job title or role", "company": "company name", "event": "event name where they met", "phone": "phone number or empty", "email": "email or empty", "linkedin": "linkedin url or empty", "notes": "anything interesting they said or discussed"}}

When a user wants to SEND, WRITE, DRAFT, or GENERATE a follow-up
message for a contact — reply ONLY with this JSON:

{{"action": "send_followup", "name": "contact name or keyword", "event": "event name", "custom_note": "any personal detail from conversation to include"}}

When a user wants to SEE, SHOW, LIST, FIND, or VIEW their contacts
or networking list — reply ONLY with this JSON:

{{"action": "view_contacts", "keyword": "search term or empty string for all"}}

When a user confirms they SENT a message (says "sent it", "done", "sent",
"I sent it") and there is a pending contact — reply ONLY with this JSON:

{{"action": "mark_sent", "contact_id": "the id from pending contact"}}

════════════════════════════════════════════
RULES
════════════════════════════════════════════

- Output ONLY the JSON for any of the above actions. No explanation.
- If user is just chatting, reply normally as a helpful friendly assistant.
- Do NOT output JSON for normal conversation.
- For contacts: extract as much as possible, leave fields empty if unknown.
- notes: capture interesting things — their startup idea, problem they mentioned,
  mutual interest — this makes the follow-up message feel personal.
"""


def get_history_path(user_id):
    return f"{HISTORY_DIR}/history_{user_id}.json"


def load_history(user_id):
    path = get_history_path(user_id)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return []


def save_history(user_id, history):
    path = get_history_path(user_id)
    with open(path, "w") as f:
        json.dump(history, f)


# ── IMAGE → TEXT via Groq vision ─────────────────────────────────────────────

async def extract_contact_from_image(image_bytes: bytes, mime_type: str) -> dict:
    """
    Send a business card image to Groq vision model.
    Returns extracted contact fields as a dict.
    Uses llama-4-scout which supports vision (free on Groq).
    """
    b64 = base64.b64encode(image_bytes).decode("utf-8")

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a business card. Extract ALL information from it. "
                            "Reply ONLY with a JSON object with these keys: "
                            "name, role, company, phone, email, linkedin, website, address. "
                            "Use empty string for any field not found. "
                            "No explanation, no markdown, just the JSON."
                        )
                    }
                ]
            }
        ]
    )

    raw = response.choices[0].message.content.strip()

    # Parse JSON from response
    try:
        json_start = raw.find("{")
        json_end = raw.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            return json.loads(raw[json_start:json_end])
    except Exception:
        pass

    # Fallback to regex extraction if JSON parse fails
    return extract_contact_from_text(raw)


# ── Chat start ────────────────────────────────────────────────────────────────

@cl.on_chat_start
async def start():
    from networking_tool import is_profile_setup, load_user_profile
    
    session_id = cl.user_session.get("id")
    user_id = str(session_id)
    cl.user_session.set("user_id", user_id)

    history = load_history(user_id)
    cl.user_session.set("history", history)

    # Check if user profile is set up
    profile_setup = is_profile_setup(user_id)
    
    if history:
        greeting = "Welcome back! I'm **Mynd** 🚀\n\n"
        
        # If profile not set up, remind them
        if not profile_setup:
            greeting += (
                "**⚠️ One quick thing:** I need your details to personalize follow-up messages.\n"
                "Say `/profile` to set up your name, LinkedIn, and Instagram.\n\n"
            )
        
        greeting += "How can I help you today?"
    else:
        greeting = (
            "Hi! I'm **Mynd**, your entrepreneur assistant 🚀\n\n"
            "**First things first:** I need YOUR information to personalize networking messages.\n"
            "Say `/profile` to set up your name, LinkedIn, Instagram, and other details.\n\n"
            "Then I'll help you with:\n"
            "📅 **Calendar** — create, view, and delete events\n"
            "🤝 **Networking** — save contacts and send personalized follow-up messages\n\n"
            "**Calendar examples:**\n"
            "- *Block thursday 7pm for Nasscom meetup*\n"
            "- *Every monday 9am team standup*\n"
            "- *What do I have on friday?*\n\n"
            "**Networking examples:**\n"
            "- *I met Rahul Sharma at Voko Run, he's a fintech founder at PayNow*\n"
            "- *Send Rahul a follow-up message*\n"
            "- *Show all my contacts*\n"
            "- *Upload a business card photo and I'll save it automatically*\n\n"
            "**Commands:**\n"
            "`/profile` — set up your personal details\n"
            "`/switchaccount` — connect a different Google account\n"
            "`/clearhistory` — reset conversation memory\n"
            "`/contacts` — show all saved contacts\n"
        )

    await cl.Message(content=greeting).send()


# ── Main message handler ──────────────────────────────────────────────────────

@cl.on_message
async def main(message: cl.Message):

    history = cl.user_session.get("history")
    user_id = cl.user_session.get("user_id")

    if history is None:
        history = []
    if user_id is None:
        user_id = "default"

    # ── COMMAND: /switchaccount ───────────────────────────────────
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
    if message.content.strip().lower() == "/clearhistory":
        history = []
        cl.user_session.set("history", [])
        save_history(user_id, [])
        await cl.Message(
            content="🧹 Conversation history cleared.\n\n"
                    "I've forgotten our previous chats. "
                    "Your calendar events and contacts are untouched."
        ).send()
        return

    # ── COMMAND: /contacts ────────────────────────────────────────
    if message.content.strip().lower() == "/contacts":
        contacts = get_all_contacts()
        await cl.Message(content=format_contacts_list(contacts)).send()
        return

    # ── HANDLE DELETION CONFIRMATION ─────────────────────────────
    if cl.user_session.get("awaiting_delete_confirm"):
        if message.content.strip().upper() == "YES":
            cl.user_session.set("awaiting_delete_confirm", False)
            pending = cl.user_session.get("pending_delete")
            try:
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
            cl.user_session.set("awaiting_delete_confirm", False)
            await cl.Message(
                content="Deletion cancelled. Your event is safe. ✅"
            ).send()
        return

    # ── HANDLE CONFLICT CONFIRMATION ─────────────────────────────
    if cl.user_session.get("awaiting_conflict_confirm"):
        if message.content.strip().upper() == "YES":
            cl.user_session.set("awaiting_conflict_confirm", False)
            pending = cl.user_session.get("pending_event")
            try:
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
            cl.user_session.set("awaiting_conflict_confirm", False)
            await cl.Message(
                content="Got it — event not created. "
                        "Give me a different time and I'll try again."
            ).send()
        return

    # ── HANDLE BUSINESS CARD IMAGE UPLOAD ────────────────────────
    # Check if user uploaded an image file (business card)
    if message.elements:
        for element in message.elements:
            # Check if it's an image
            if hasattr(element, "mime") and element.mime and element.mime.startswith("image/"):
                await cl.Message(
                    content="📸 Got your business card! Scanning it now..."
                ).send()

                try:
                    # Read the image bytes
                    with open(element.path, "rb") as f:
                        image_bytes = f.read()

                    # Extract contact info using Groq vision
                    extracted = await extract_contact_from_image(
                        image_bytes, element.mime
                    )

                    # Ask user for event context if not in message
                    event_context = message.content.strip() if message.content.strip() else ""

                    # Merge any event info the user typed with extracted data
                    if event_context:
                        extracted["notes"] = event_context

                    # Show what was extracted and ask for confirmation
                    cl.user_session.set("pending_contact", extracted)
                    cl.user_session.set("awaiting_contact_confirm", True)

                    preview = "\n".join([
                        f"**{k.title()}:** {v}"
                        for k, v in extracted.items()
                        if v and k not in ["notes"]
                    ])

                    await cl.Message(
                        content=f"✅ Here's what I extracted from the card:\n\n"
                                f"{preview}\n\n"
                                f"Which event did you meet them at? "
                                f"(e.g. *Voko Run*, *Nasscom*, *TiE Chennai*)\n\n"
                                f"Or type **SAVE** to save as-is."
                    ).send()
                    return

                except Exception as e:
                    await cl.Message(
                        content=f"Couldn't read the card: {str(e)}\n\n"
                                f"Try typing the contact details instead — "
                                f"name, company, role, phone etc."
                    ).send()
                    return

    # ── HANDLE CONTACT IMAGE CONFIRMATION ────────────────────────
    if cl.user_session.get("awaiting_contact_confirm"):
        pending = cl.user_session.get("pending_contact")
        user_input = message.content.strip()

        if user_input.upper() == "SAVE":
            # Save without adding event name
            saved = add_contact(pending)
            cl.user_session.set("awaiting_contact_confirm", False)
            cl.user_session.set("last_saved_contact", saved)
            await cl.Message(
                content=f"✅ Contact saved!\n\n"
                        f"{format_contact_card(saved)}\n\n"
                        f"Say **send followup to {saved.get('name', 'them')}** "
                        f"when you want to generate a message."
            ).send()
        else:
            # User typed event name
            pending["event"] = user_input
            saved = add_contact(pending)
            cl.user_session.set("awaiting_contact_confirm", False)
            cl.user_session.set("last_saved_contact", saved)
            await cl.Message(
                content=f"✅ Contact saved from **{user_input}**!\n\n"
                        f"{format_contact_card(saved)}\n\n"
                        f"Say **send followup to {saved.get('name', 'them')}** "
                        f"when you're ready."
            ).send()
        return

    # ── NORMAL MESSAGE FLOW ───────────────────────────────────────

    history.append({
        "role": "user",
        "content": message.content
    })

    full_messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ] + history

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=700,
        messages=full_messages
    )

    reply = response.choices[0].message.content.strip()

    # Try to parse JSON action from Groq reply
    event_data = None
    try:
        json_start = reply.find("{")
        json_end = reply.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            json_str = reply[json_start:json_end]
            parsed = json.loads(json_str)
            if parsed.get("action") in [
                "create_event", "delete_event", "view_events",
                "save_contact", "send_followup", "view_contacts", "mark_sent"
            ]:
                event_data = parsed
    except json.JSONDecodeError:
        pass

    if event_data:
        action = event_data.get("action")

        # ── CALENDAR: CREATE EVENT ────────────────────────────────
        if action == "create_event":

            if not event_data.get("time") or event_data.get("time").strip() == "":
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

            duration_minutes = resolve_duration(
                str(event_data.get("duration", "1 hour"))
            )

            conflicts = check_conflicts(
                user_id=user_id,
                date_input=event_data["date"],
                time_input=event_data["time"],
                duration_minutes=duration_minutes
            )

            if conflicts:
                conflict_list = "\n".join(
                    [f"- {e.get('summary', 'Untitled')}" for e in conflicts]
                )
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
                result = create_calendar_event(
                    user_id=user_id,
                    title=event_data["title"],
                    date_input=event_data["date"],
                    time_input=event_data["time"],
                    duration_minutes=duration_minutes,
                    reminder_minutes=int(event_data.get("reminder", 30)),
                    recurrence=event_data.get("recurrence")
                )
                reply = result
            except Exception as e:
                reply = (
                    f"I understood the event but ran into an issue: {str(e)}\n\n"
                    f"Make sure credentials.json is in your project folder."
                )

        # ── CALENDAR: DELETE EVENT ────────────────────────────────
        elif action == "delete_event":
            cl.user_session.set("pending_delete", event_data)
            cl.user_session.set("awaiting_delete_confirm", True)
            reply = (
                f"Are you sure you want to delete this event?\n\n"
                f"📌 **{event_data['title']}**\n"
                f"📅 Date: {event_data['date']}\n\n"
                f"Type **YES** to confirm or **NO** to cancel."
            )

        # ── CALENDAR: VIEW EVENTS ─────────────────────────────────
        elif action == "view_events":
            try:
                result = get_events(
                    user_id=user_id,
                    date_input=event_data["date"]
                )
                reply = result
            except Exception as e:
                reply = f"Couldn't fetch your calendar: {str(e)}"

        # ── NETWORKING: SAVE CONTACT ──────────────────────────────
        elif action == "save_contact":
            try:
                saved = add_contact(event_data)
                cl.user_session.set("last_saved_contact", saved)
                reply = (
                    f"✅ Contact saved!\n\n"
                    f"{format_contact_card(saved)}\n\n"
                    f"Say **send followup to {saved.get('name', 'them')}** "
                    f"when you want to generate the message."
                )
            except Exception as e:
                reply = f"Couldn't save contact: {str(e)}"

        # ── NETWORKING: GENERATE FOLLOW-UP MESSAGE ────────────────
        elif action == "send_followup":
            name_keyword = event_data.get("name", "")
            event_name = event_data.get("event", "")
            custom_note = event_data.get("custom_note", "")

            # Find the contact
            matches = search_contacts(name_keyword)

            if not matches:
                reply = (
                    f"❌ Couldn't find a contact matching **{name_keyword}**.\n\n"
                    f"Try saying the full name or say `/contacts` to see everyone."
                )
            else:
                contact = matches[0]  # Use best match
                cl.user_session.set("last_followup_contact", contact)

                # Generate the personalised message
                msg = generate_followup_message(
                    contact=contact,
                    event_name=event_name or contact.get("event", ""),
                    custom_note=custom_note
                )

                cl.user_session.set("pending_followup_message", msg)
                cl.user_session.set("pending_followup_contact_id", contact.get("id"))

                reply = (
                    f"✉️ Here's your follow-up message for **{contact.get('name')}**:\n\n"
                    f"---\n\n"
                    f"{msg}\n\n"
                    f"---\n\n"
                    f"📋 **Copy this message** and send it on WhatsApp or LinkedIn.\n\n"
                    f"Say **sent it** once you've sent it and I'll mark it done. ✅"
                )

        # ── NETWORKING: VIEW CONTACTS ─────────────────────────────
        elif action == "view_contacts":
            keyword = event_data.get("keyword", "").strip()
            if keyword:
                matches = search_contacts(keyword)
                reply = format_contacts_list(matches)
                if matches:
                    reply = f"🔍 Results for **'{keyword}'**:\n\n" + reply
            else:
                contacts = get_all_contacts()
                reply = format_contacts_list(contacts)

        # ── NETWORKING: MARK MESSAGE SENT ─────────────────────────
        elif action == "mark_sent":
            contact_id = event_data.get("contact_id", "")

            # Fallback: use last pending contact id from session
            if not contact_id:
                contact_id = cl.user_session.get("pending_followup_contact_id", "")

            if contact_id:
                mark_message_sent(contact_id, platform="whatsapp/linkedin")
                reply = (
                    f"✅ Marked as sent! Great networking, Suriya 🤝\n\n"
                    f"I've logged this follow-up in your contacts."
                )
            else:
                reply = "✅ Got it — logged the follow-up. Keep it up! 🤝"

    # Add reply to history and save
    history.append({
        "role": "assistant",
        "content": reply
    })

    cl.user_session.set("history", history)
    save_history(user_id, history)

    await cl.Message(content=reply).send()
