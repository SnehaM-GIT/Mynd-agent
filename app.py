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
    format_networking_stats,
    format_profile_card,
    load_user_profile,
    save_user_profile,
    import_legacy_data,
)
from daily_brief import generate_daily_brief
from microsoft_calendar_tool import (
    MicrosoftCalendarNotConnected,
    check_microsoft_conflicts,
    clear_microsoft_token,
    create_microsoft_calendar_event,
    delete_microsoft_calendar_event,
    finish_microsoft_device_login,
    get_microsoft_events,
    is_microsoft_connected,
    start_microsoft_device_login,
)
from application_tool import (
    draft_application,
    format_application_draft,
    format_application_drafts,
    format_vault_summary,
    parse_private_info_updates,
    save_private_info_updates,
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

{{"action": "create_event", "title": "event name", "date": "as user said", "time": "as user said or empty string if not mentioned", "duration": "as user said or 1 hour if not mentioned", "reminder": 30, "recurrence": null, "provider": "google"}}

Use provider "microsoft" when the user says Microsoft, Outlook, or Office 365
calendar. Otherwise use "google".

For RECURRING events like "every monday", "every week", "daily standup",
"every month" — include recurrence like this:

{{"action": "create_event", "title": "event name", "date": "as user said", "time": "as user said", "duration": "1 hour", "reminder": 30, "recurrence": {{"frequency": "weekly", "count": 10}}, "provider": "google"}}

recurrence frequency must be: "daily", "weekly", or "monthly"

When a user wants to DELETE, REMOVE, or CANCEL an event:
{{"action": "delete_event", "title": "event keyword", "date": "as user said", "provider": "google"}}

When a user wants to VIEW their calendar for a day:
{{"action": "view_events", "date": "as user said", "provider": "google"}}

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

APPLICATION + PRIVATE INFO ACTIONS

When a user asks you to remember private application, identity, founder,
startup, company, tax, banking, or profile details for future forms,
reply ONLY with this JSON:

{{"action": "save_private_info", "fields": {{"startup_name": "value", "city": "value"}}}}

When a user asks you to fill, prepare, draft, or answer an application
or form using saved information, reply ONLY with this JSON:

{{"action": "draft_application", "request": "the user's full request including form name and fields"}}

Never invent private identity, business, tax, banking, or application data.
Unknown fields should remain missing for the application draft.

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


PROFILE_FIELDS = {
    "name", "email", "phone", "university", "domains",
    "org", "linkedin", "instagram", "tagline",
}


PROFILE_ONBOARDING_FIELDS = [
    (
        "name",
        "What is your full name? This will appear in follow-up messages.",
        True,
    ),
    (
        "email",
        "What email should Mynd use for applications and contact info? Type `skip` to leave it blank.",
        False,
    ),
    (
        "phone",
        "What phone number should Mynd remember? Type `skip` to leave it blank.",
        False,
    ),
    (
        "university",
        "University, company, or primary affiliation? Type `skip` if not relevant.",
        False,
    ),
    (
        "domains",
        "What domains do you work in? Example: chemical engineering, finance, SaaS.",
        False,
    ),
    (
        "org",
        "Any organization, incubator, investor network, or company to mention? Type `skip` if none.",
        False,
    ),
    (
        "linkedin",
        "Paste your LinkedIn URL. Type `skip` if you do not want to add it now.",
        False,
    ),
    (
        "instagram",
        "Paste your Instagram URL. Type `skip` if you do not want to add it now.",
        False,
    ),
    (
        "tagline",
        "One short line about how you help people. This becomes your follow-up message value line.",
        False,
    ),
]


def get_current_user_id():
    """
    Stable local identity for this Mynd workspace.
    For a real company deployment, set MYND_USER_ID per logged-in user.
    """
    raw = os.getenv("MYND_USER_ID") or os.getenv("MYND_WORKSPACE_ID") or "local_user"
    user_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", raw.strip())
    return user_id or "local_user"


def parse_profile_updates(command_text):
    body = re.sub(r"^/profile\s*(set)?", "", command_text, flags=re.I).strip()
    if not body:
        return {}

    updates = {}
    parts = re.split(r"\s*\|\s*|\n+", body)
    for part in parts:
        if not part.strip():
            continue
        if "=" in part:
            key, value = part.split("=", 1)
        elif ":" in part:
            key, value = part.split(":", 1)
        else:
            continue
        key = key.strip().lower()
        value = value.strip()
        if key in PROFILE_FIELDS and value:
            updates[key] = value
    return updates


def get_ask_output(answer):
    if not answer:
        return ""
    if isinstance(answer, dict):
        return str(answer.get("output", "")).strip()
    return str(answer).strip()


async def run_profile_onboarding(user_id, force=False):
    profile = load_user_profile(user_id)
    updates = {}

    intro = (
        "Let's set up your profile once so Mynd can personalize follow-ups, "
        "applications, and calendar messages. Your answers are saved locally "
        "in encrypted storage.\n\n"
        "You can type `skip` for optional fields."
    )
    if force:
        intro = "Let's update your saved Mynd profile.\n\n" + intro
    await cl.Message(content=intro).send()

    for key, prompt, required in PROFILE_ONBOARDING_FIELDS:
        existing = str(profile.get(key, "") or "").strip()
        if existing and not force:
            continue

        label = prompt
        if existing:
            label += f"\n\nCurrent value: `{existing}`"

        answer = await cl.AskUserMessage(
            content=label,
            timeout=300,
            raise_on_timeout=False,
        ).send()
        value = get_ask_output(answer)

        if value.lower() in ["skip", ""]:
            if required and not existing:
                await cl.Message(
                    content="Name is required so your messages do not look generic. You can run `/setup` later."
                ).send()
                continue
            continue

        updates[key] = value

    if updates:
        profile.update(updates)

    profile["setup_complete"] = bool(profile.get("name")) and bool(
        profile.get("linkedin") or profile.get("instagram") or profile.get("email")
    )
    save_user_profile(user_id, profile)

    if profile["setup_complete"]:
        await cl.Message(
            content="Profile setup complete.\n\n" + format_profile_card(profile)
        ).send()
    else:
        await cl.Message(
            content=(
                "Profile saved, but it is not complete yet. Add at least your name "
                "and one contact link/email when you are ready.\n\n"
                + format_profile_card(profile)
            )
        ).send()

    return profile


def calendar_provider_from(event_data, message_text, session_provider):
    provider = (event_data or {}).get("provider", "") or session_provider or "google"
    text = f"{message_text} {json.dumps(event_data or {})}".lower()
    if any(word in text for word in ["microsoft", "outlook", "office 365", "office365"]):
        provider = "microsoft"
    if "google" in text:
        provider = "google"
    return "microsoft" if provider == "microsoft" else "google"


def calendar_label(provider):
    return "Microsoft Calendar" if provider == "microsoft" else "Google Calendar"


def parse_local_text_action(text):
    """Cheap deterministic parser for the most common text workflows."""
    clean = text.strip()
    lower = clean.lower()

    if lower in ["sent it", "done", "sent", "i sent it"]:
        return {"action": "mark_sent", "contact_id": ""}

    followup_match = re.search(
        r"\b(?:send|write|draft|generate)\s+(?:a\s+)?(?:follow[- ]?up\s+)?(?:message\s+)?(?:to|for)\s+([a-z][\w .'-]+)",
        clean,
        re.I,
    )
    if not followup_match:
        followup_match = re.search(
            r"\b(?:send|write|draft|generate)\s+([a-z][\w .'-]+?)\s+(?:a\s+)?follow[- ]?up(?:\s+message)?\b",
            clean,
            re.I,
        )
    if not followup_match:
        followup_match = re.search(
            r"\b(?:send|write|draft|generate)\s+([a-z][\w .'-]+?)\s+(?:a\s+)?message\b",
            clean,
            re.I,
        )
    if followup_match:
        name = followup_match.group(1).strip(" .")
        name = re.sub(r"\s+(?:on|via)\s+(?:whatsapp|linkedin|email).*", "", name, flags=re.I)
        return {
            "action": "send_followup",
            "name": name,
            "event": "",
            "custom_note": "",
        }

    if any(phrase in lower for phrase in ["show contacts", "see contacts", "list contacts", "view contacts"]):
        keyword = ""
        from_match = re.search(r"\bfrom\s+(.+)$", clean, re.I)
        if from_match:
            keyword = from_match.group(1).strip(" .")
        return {"action": "view_contacts", "keyword": keyword}

    contact = parse_manual_contact(clean)
    if contact:
        contact["action"] = "save_contact"
        return contact

    return None


def parse_manual_contact(text):
    lower = text.lower()
    if "met " not in lower and "meet " not in lower:
        return None

    contact = extract_contact_from_text(text)

    name_match = re.search(
        r"\b(?:i\s+)?met\s+([A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,3})",
        text,
    )
    if name_match:
        contact["name"] = name_match.group(1).strip()

    event_match = re.search(
        r"\bat\s+([^.,\n]+?)(?:\s+(?:he|she|they|who|and)\b|[.,\n]|$)",
        text,
        re.I,
    )
    if event_match:
        contact["event"] = event_match.group(1).strip()

    role_company_match = re.search(
        r"\b(?:he|she|they)\s+(?:is|was|are)\s+(?:a|an)?\s*(.+?)\s+(?:at|from|with)\s+([A-Z][\w &-]+?)(?:[.,\n]|$)",
        text,
        re.I,
    )
    if role_company_match:
        contact["role"] = role_company_match.group(1).strip(" .")
        contact["company"] = role_company_match.group(2).strip(" .")

    founder_match = re.search(r"\bfounder\s+at\s+([A-Z][\w &-]+?)(?:[.,\n]|$)", text, re.I)
    if founder_match and not contact.get("role"):
        contact["role"] = "founder"
        contact["company"] = founder_match.group(1).strip(" .")

    if contact.get("name"):
        contact.setdefault("role", "")
        contact.setdefault("company", "")
        contact.setdefault("event", "")
        contact.setdefault("phone", "")
        contact.setdefault("email", "")
        contact.setdefault("linkedin", "")
        contact["notes"] = text
        return contact
    return None


def provider_check_conflicts(provider, user_id, date_input, time_input, duration_minutes):
    if provider == "microsoft":
        return check_microsoft_conflicts(user_id, date_input, time_input, duration_minutes)
    return check_conflicts(user_id, date_input, time_input, duration_minutes)


def provider_create_event(provider, user_id, event_data, duration_minutes):
    kwargs = dict(
        user_id=user_id,
        title=event_data["title"],
        date_input=event_data["date"],
        time_input=event_data["time"],
        duration_minutes=duration_minutes,
        reminder_minutes=int(event_data.get("reminder", 30)),
        recurrence=event_data.get("recurrence"),
    )
    if provider == "microsoft":
        return create_microsoft_calendar_event(**kwargs)
    return create_calendar_event(**kwargs)


def provider_delete_event(provider, user_id, title_keyword, date_input):
    if provider == "microsoft":
        return delete_microsoft_calendar_event(user_id, title_keyword, date_input)
    return delete_calendar_event(user_id, title_keyword, date_input)


def provider_get_events(provider, user_id, date_input):
    if provider == "microsoft":
        return get_microsoft_events(user_id, date_input)
    return get_events(user_id, date_input)


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
    
    user_id = get_current_user_id()
    cl.user_session.set("user_id", user_id)
    cl.user_session.set("calendar_provider", "google")

    history = load_history(user_id)
    cl.user_session.set("history", history)

    # Check if user profile is set up
    profile_setup = is_profile_setup(user_id)

    if not profile_setup:
        await run_profile_onboarding(user_id)
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
            "`/usegoogle` / `/usemicrosoft` — choose calendar provider\n"
            "`/microsoftcalendar` — connect Outlook/Microsoft Calendar\n"
            "`/stats` — networking stats\n"
            "`/brief` — daily brief\n"
            "`/importlegacydata` — import old local JSON profile/contacts\n"
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
        user_id = get_current_user_id()
        cl.user_session.set("user_id", user_id)

    text = message.content.strip()
    lower_text = text.lower()

    if lower_text in ["/setup", "/onboarding"]:
        await run_profile_onboarding(user_id, force=True)
        return

    if lower_text == "/whoami":
        profile = load_user_profile(user_id)
        await cl.Message(
            content=(
                f"Workspace user: `{user_id}`\n\n"
                f"{format_profile_card(profile)}"
            )
        ).send()
        return

    if cl.user_session.get("awaiting_microsoft_login") and lower_text in ["done", "yes", "connected"]:
        flow = cl.user_session.get("microsoft_device_flow")
        try:
            connected, result_message = finish_microsoft_device_login(user_id, flow)
        except Exception as e:
            connected, result_message = False, f"Microsoft login error: {str(e)}"
        if connected:
            cl.user_session.set("awaiting_microsoft_login", False)
            cl.user_session.set("microsoft_device_flow", None)
            cl.user_session.set("calendar_provider", "microsoft")
        await cl.Message(content=result_message).send()
        return

    if lower_text.startswith("/profile"):
        updates = parse_profile_updates(text)
        profile = load_user_profile(user_id)
        if updates:
            profile.update(updates)
            profile["setup_complete"] = True
            save_user_profile(user_id, profile)
            content = "Profile updated.\n\n" + format_profile_card(profile)
        else:
            content = (
                format_profile_card(profile)
                + "\n\nUpdate it like this:\n"
                + "`/profile name=Suriya Jayan | linkedin=https://... | "
                + "instagram=https://... | domains=chemical engineering and finance`"
            )
        await cl.Message(content=content).send()
        return

    if lower_text == "/stats":
        await cl.Message(content=format_networking_stats(user_id=user_id)).send()
        return

    if lower_text == "/brief":
        await cl.Message(content=generate_daily_brief(user_id=user_id)).send()
        return

    if lower_text == "/vault reveal":
        await cl.Message(content=format_vault_summary(user_id=user_id, reveal=True)).send()
        return

    if lower_text.startswith("/vault"):
        updates = parse_private_info_updates(text)
        if updates:
            count = save_private_info_updates(user_id, updates)
            content = (
                f"Saved {count} private field(s) to the encrypted vault.\n\n"
                + format_vault_summary(user_id=user_id)
            )
        else:
            content = format_vault_summary(user_id=user_id)
        await cl.Message(content=content).send()
        return

    if lower_text == "/applications":
        await cl.Message(content=format_application_drafts(user_id=user_id)).send()
        return

    if lower_text.startswith("/application"):
        draft = draft_application(user_id, text)
        await cl.Message(content=format_application_draft(draft)).send()
        return

    if lower_text == "/importlegacydata":
        result = import_legacy_data(user_id)
        await cl.Message(
            content=(
                "Legacy JSON import complete.\n\n"
                f"Profile imported: {'yes' if result['profile'] else 'no'}\n"
                f"Contacts imported: {result['contacts']}"
            )
        ).send()
        return

    if lower_text == "/usegoogle":
        cl.user_session.set("calendar_provider", "google")
        await cl.Message(content="Google Calendar selected for calendar actions.").send()
        return

    if lower_text == "/usemicrosoft":
        cl.user_session.set("calendar_provider", "microsoft")
        if is_microsoft_connected(user_id):
            content = "Microsoft Calendar selected for calendar actions."
        else:
            content = (
                "Microsoft Calendar selected, but it is not connected yet.\n\n"
                "Run `/microsoftcalendar` to connect your Outlook/Microsoft account."
            )
        await cl.Message(content=content).send()
        return

    if lower_text == "/calendar":
        provider = cl.user_session.get("calendar_provider") or "google"
        ms_status = "connected" if is_microsoft_connected(user_id) else "not connected"
        await cl.Message(
            content=(
                f"Current calendar provider: **{provider}**\n\n"
                f"Microsoft Calendar: {ms_status}\n"
                "Use `/usegoogle`, `/usemicrosoft`, or `/microsoftcalendar`."
            )
        ).send()
        return

    if lower_text == "/microsoftcalendar":
        try:
            flow = start_microsoft_device_login(user_id)
            cl.user_session.set("microsoft_device_flow", flow)
            cl.user_session.set("awaiting_microsoft_login", True)
            content = (
                "Connect Microsoft Calendar:\n\n"
                f"1. Open {flow.get('verification_uri')}\n"
                f"2. Enter code `{flow.get('user_code')}`\n"
                "3. Approve calendar access\n"
                "4. Come back here and type **DONE**"
            )
        except Exception as e:
            content = f"Could not start Microsoft login: {str(e)}"
        await cl.Message(content=content).send()
        return

    if lower_text == "/switchmicrosoft":
        was_connected = clear_microsoft_token(user_id)
        cl.user_session.set("calendar_provider", "microsoft")
        content = (
            "Microsoft account disconnected. Run `/microsoftcalendar` to connect again."
            if was_connected else
            "No Microsoft account was connected. Run `/microsoftcalendar` to connect one."
        )
        await cl.Message(content=content).send()
        return

    # ── COMMAND: /switchaccount ───────────────────────────────────
    if cl.user_session.get("awaiting_event_time"):
        pending = cl.user_session.get("pending_event")
        provider = pending.get("provider") or cl.user_session.get("calendar_provider") or "google"
        pending["time"] = text
        pending["provider"] = provider
        cl.user_session.set("awaiting_event_time", False)
        duration_minutes = resolve_duration(str(pending.get("duration", "1 hour")))
        try:
            result = provider_create_event(provider, user_id, pending, duration_minutes)
        except Exception as e:
            result = f"Couldn't create this {calendar_label(provider)} event: {str(e)}"
        await cl.Message(content=result).send()
        return

    if lower_text == "/switchaccount":
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
        contacts = get_all_contacts(user_id=user_id)
        await cl.Message(content=format_contacts_list(contacts)).send()
        return

    # ── HANDLE DELETION CONFIRMATION ─────────────────────────────
    if cl.user_session.get("awaiting_delete_confirm"):
        if message.content.strip().upper() == "YES":
            cl.user_session.set("awaiting_delete_confirm", False)
            pending = cl.user_session.get("pending_delete")
            try:
                provider = pending.get("provider") or cl.user_session.get("calendar_provider") or "google"
                result = provider_delete_event(
                    provider, user_id, pending["title"], pending["date"]
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
                provider = pending.get("provider") or cl.user_session.get("calendar_provider") or "google"
                duration_minutes = resolve_duration(
                    str(pending.get("duration", "1 hour"))
                )
                result = provider_create_event(provider, user_id, pending, duration_minutes)
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
            saved = add_contact(pending, user_id=user_id)
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
            saved = add_contact(pending, user_id=user_id)
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

    event_data = parse_local_text_action(message.content)
    reply = ""

    if not event_data:
        full_messages = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ] + history

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=700,
                messages=full_messages
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            reply = (
                "I received your message, but the AI routing call failed before "
                f"I could act on it: {str(e)}\n\n"
                "Try a direct command like `/contacts`, `/profile`, or "
                "`/vault set startup_name=...` while I recover."
            )

        # Try to parse JSON action from Groq reply
        try:
            json_start = reply.find("{")
            json_end = reply.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_str = reply[json_start:json_end]
                parsed = json.loads(json_str)
                if parsed.get("action") in [
                    "create_event", "delete_event", "view_events",
                    "save_contact", "send_followup", "view_contacts", "mark_sent",
                    "save_private_info", "draft_application"
                ]:
                    event_data = parsed
        except json.JSONDecodeError:
            pass

    if event_data:
        action = event_data.get("action")

        # ── CALENDAR: CREATE EVENT ────────────────────────────────
        if action == "create_event":
            provider = calendar_provider_from(
                event_data,
                message.content,
                cl.user_session.get("calendar_provider"),
            )
            event_data["provider"] = provider

            if not event_data.get("time") or event_data.get("time").strip() == "":
                cl.user_session.set("pending_event", event_data)
                cl.user_session.set("awaiting_event_time", True)
                reply = (
                    f"Got it! I have your event **{event_data['title']}** "
                    f"on **{event_data['date']}** in {calendar_label(provider)}.\n\n"
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

            try:
                conflicts = provider_check_conflicts(
                    provider,
                    user_id=user_id,
                    date_input=event_data["date"],
                    time_input=event_data["time"],
                    duration_minutes=duration_minutes
                )
            except Exception as e:
                reply = f"Couldn't check {calendar_label(provider)} conflicts: {str(e)}"
                history.append({"role": "assistant", "content": reply})
                cl.user_session.set("history", history)
                save_history(user_id, history)
                await cl.Message(content=reply).send()
                return

            if conflicts:
                conflict_list = "\n".join(
                    [
                        f"- {e.get('summary') or e.get('subject') or 'Untitled'}"
                        for e in conflicts
                    ]
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
                        f"Calendar: {calendar_label(provider)}\n"
                        f"📅 Date: {event_data['date']}\n"
                        f"⏰ Time: {event_data['time']}\n"
                        f"⏱ Duration: {duration_text}\n"
                        f"🔔 Reminder: {event_data['reminder']} mins before"
                        f"{recurrence_info}\n\n"
                        f"Creating now..."
            ).send()

            try:
                result = provider_create_event(provider, user_id, event_data, duration_minutes)
                reply = result
            except Exception as e:
                reply = (
                    f"I understood the event but ran into an issue with "
                    f"{calendar_label(provider)}: {str(e)}"
                )

        # ── CALENDAR: DELETE EVENT ────────────────────────────────
        elif action == "delete_event":
            provider = calendar_provider_from(
                event_data,
                message.content,
                cl.user_session.get("calendar_provider"),
            )
            event_data["provider"] = provider
            cl.user_session.set("pending_delete", event_data)
            cl.user_session.set("awaiting_delete_confirm", True)
            reply = (
                f"Are you sure you want to delete this event?\n\n"
                f"📌 **{event_data['title']}**\n"
                f"Calendar: {calendar_label(provider)}\n"
                f"📅 Date: {event_data['date']}\n\n"
                f"Type **YES** to confirm or **NO** to cancel."
            )

        # ── CALENDAR: VIEW EVENTS ─────────────────────────────────
        elif action == "view_events":
            try:
                provider = calendar_provider_from(
                    event_data,
                    message.content,
                    cl.user_session.get("calendar_provider"),
                )
                result = provider_get_events(provider, user_id, event_data["date"])
                reply = result
            except Exception as e:
                reply = f"Couldn't fetch your calendar: {str(e)}"

        # ── NETWORKING: SAVE CONTACT ──────────────────────────────
        elif action == "save_contact":
            try:
                saved = add_contact(event_data, user_id=user_id)
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
            matches = search_contacts(name_keyword, user_id=user_id)

            if not matches:
                reply = (
                    f"❌ Couldn't find a contact matching **{name_keyword}**.\n\n"
                    f"Try saying the full name or say `/contacts` to see everyone."
                )
            else:
                contact = matches[0]  # Use best match
                cl.user_session.set("last_followup_contact", contact)

                # Generate the personalised message
                msg, profile_complete, missing_fields = generate_followup_message(
                    contact=contact,
                    event_name=event_name or contact.get("event", ""),
                    custom_note=custom_note,
                    user_id=user_id,
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
                matches = search_contacts(keyword, user_id=user_id)
                reply = format_contacts_list(matches)
                if matches:
                    reply = f"🔍 Results for **'{keyword}'**:\n\n" + reply
            else:
                contacts = get_all_contacts(user_id=user_id)
                reply = format_contacts_list(contacts)

        # ── NETWORKING: MARK MESSAGE SENT ─────────────────────────
        elif action == "mark_sent":
            contact_id = event_data.get("contact_id", "")

            # Fallback: use last pending contact id from session
            if not contact_id:
                contact_id = cl.user_session.get("pending_followup_contact_id", "")

            if contact_id:
                mark_message_sent(contact_id, platform="whatsapp/linkedin", user_id=user_id)
                reply = (
                    f"✅ Marked as sent! Great networking, Suriya 🤝\n\n"
                    f"I've logged this follow-up in your contacts."
                )
            else:
                reply = "✅ Got it — logged the follow-up. Keep it up! 🤝"

        elif action == "save_private_info":
            fields = event_data.get("fields", {})
            if isinstance(fields, dict) and fields:
                count = save_private_info_updates(user_id, fields)
                reply = (
                    f"Saved {count} private field(s) to the encrypted vault.\n\n"
                    f"{format_vault_summary(user_id=user_id)}"
                )
            else:
                reply = (
                    "I could not find specific fields to save. Use this format:\n"
                    "`/vault set startup_name=Acme Labs | city=Chennai`"
                )

        elif action == "draft_application":
            request_text = event_data.get("request") or message.content
            draft = draft_application(user_id, request_text)
            reply = format_application_draft(draft)

    # Add reply to history and save
    history.append({
        "role": "assistant",
        "content": reply
    })

    cl.user_session.set("history", history)
    save_history(user_id, history)

    await cl.Message(content=reply).send()
