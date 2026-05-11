import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from application_tool import (
    draft_application,
    format_application_draft,
    format_application_drafts,
    format_vault_summary,
    parse_private_info_updates,
    save_private_info_updates,
)
from calendar_tool import resolve_duration
from networking_tool import (
    add_contact,
    format_contact_card,
    format_contacts_list,
    format_networking_stats,
    format_profile_card,
    generate_followup_message,
    get_all_contacts,
    load_user_profile,
    mark_message_sent,
    save_user_profile,
    search_contacts,
    extract_contact_from_text,
)


APP_DIR = Path(__file__).parent
USER_ID = re.sub(
    r"[^a-zA-Z0-9_.-]+",
    "_",
    (os.getenv("MYND_USER_ID") or os.getenv("MYND_WORKSPACE_ID") or "local_user").strip(),
) or "local_user"

app = FastAPI(title="Mynd Entrepreneur Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


class ProfilePayload(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    university: str = ""
    domains: str = ""
    org: str = ""
    linkedin: str = ""
    instagram: str = ""
    tagline: str = ""


class ChatPayload(BaseModel):
    message: str


@app.get("/", response_class=HTMLResponse)
def index():
    return (APP_DIR / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/api/profile")
def get_profile():
    profile = load_user_profile(USER_ID)
    profile["completion"] = profile_completion(profile)
    profile["user_id"] = USER_ID
    return profile


@app.post("/api/profile")
def save_profile(payload: ProfilePayload):
    profile = payload.model_dump()
    profile["setup_complete"] = is_complete_profile(profile)
    save_user_profile(USER_ID, profile)
    profile["completion"] = profile_completion(profile)
    profile["user_id"] = USER_ID
    return profile


@app.get("/api/contacts")
def contacts():
    return {"contacts": get_all_contacts(user_id=USER_ID)}


@app.post("/api/chat")
def chat(payload: ChatPayload):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    action = parse_intent(message)
    reply = handle_action(action, message)
    return {"reply": reply, "action": action.get("action", "chat")}


def profile_completion(profile: dict) -> dict:
    required = ["name", "email", "phone", "linkedin", "tagline"]
    filled = [field for field in required if profile.get(field)]
    return {
        "filled": len(filled),
        "total": len(required),
        "percent": int((len(filled) / len(required)) * 100),
        "missing": [field for field in required if not profile.get(field)],
        "complete": is_complete_profile(profile),
    }


def is_complete_profile(profile: dict) -> bool:
    return bool(profile.get("name")) and bool(
        profile.get("email") or profile.get("linkedin") or profile.get("instagram")
    )


def parse_intent(text: str) -> dict:
    lower = text.lower().strip()

    if lower in ["sent it", "done", "i sent it", "message sent"]:
        return {"action": "mark_sent"}

    if any(phrase in lower for phrase in ["show contacts", "list contacts", "see contacts", "all contacts"]):
        keyword = ""
        match = re.search(r"\bfrom\s+(.+)$", text, re.I)
        if match:
            keyword = match.group(1).strip(" .")
        return {"action": "view_contacts", "keyword": keyword}

    followup = re.search(
        r"\b(?:send|write|draft|generate)\s+(?:a\s+)?(?:follow[- ]?up\s+)?(?:message\s+)?(?:to|for)\s+([a-z][\w .'-]+)",
        text,
        re.I,
    )
    if not followup:
        followup = re.search(
            r"\b(?:send|write|draft|generate)\s+([a-z][\w .'-]+?)\s+(?:a\s+)?follow[- ]?up(?:\s+message)?\b",
            text,
            re.I,
        )
    if not followup:
        followup = re.search(
            r"\b(?:send|write|draft|generate)\s+([a-z][\w .'-]+?)\s+(?:a\s+)?message\b",
            text,
            re.I,
        )
    if followup:
        return {"action": "send_followup", "name": followup.group(1).strip(" .")}

    if any(word in lower for word in ["application", "form", "grant", "apply"]):
        return {"action": "draft_application", "request": text}

    if any(phrase in lower for phrase in ["remember this", "save this", "store this", "private info"]):
        updates = parse_private_info_updates(text)
        if updates:
            return {"action": "save_private_info", "fields": updates}

    if lower.startswith("save ") and ("=" in text or ":" in text):
        updates = parse_private_info_updates(text.replace("save ", "/vault set ", 1))
        if updates:
            return {"action": "save_private_info", "fields": updates}

    contact = parse_contact(text)
    if contact:
        contact["action"] = "save_contact"
        return contact

    if any(word in lower for word in ["schedule", "block", "calendar", "meeting", "event"]):
        return {"action": "calendar_help"}

    if any(phrase in lower for phrase in ["networking stats", "follow-up rate", "stats"]):
        return {"action": "stats"}

    if any(phrase in lower for phrase in ["what can you do", "help", "features"]):
        return {"action": "intro"}

    return {"action": "intro"}


def parse_contact(text: str) -> dict | None:
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

    if not contact.get("name"):
        return None

    contact.setdefault("role", "")
    contact.setdefault("company", "")
    contact.setdefault("event", "")
    contact.setdefault("phone", "")
    contact.setdefault("email", "")
    contact.setdefault("linkedin", "")
    contact["notes"] = text
    return contact


def handle_action(action: dict, original_text: str) -> str:
    kind = action.get("action")

    if kind == "save_contact":
        saved = add_contact(action, user_id=USER_ID)
        return (
            "Contact saved.\n\n"
            f"{format_contact_card(saved)}\n\n"
            f"Try: send {saved.get('name', 'them')} a follow-up message"
        )

    if kind == "view_contacts":
        keyword = action.get("keyword", "")
        if keyword:
            return format_contacts_list(search_contacts(keyword, user_id=USER_ID))
        return format_contacts_list(get_all_contacts(user_id=USER_ID))

    if kind == "send_followup":
        matches = search_contacts(action.get("name", ""), user_id=USER_ID)
        if not matches:
            return "I could not find that contact yet. Add them first by typing who you met and where."
        contact = matches[0]
        message, complete, _ = generate_followup_message(
            contact=contact,
            event_name=contact.get("event", ""),
            custom_note="",
            user_id=USER_ID,
        )
        return f"Here is a follow-up for {contact.get('name')}:\n\n{message}"

    if kind == "mark_sent":
        contacts = [c for c in get_all_contacts(user_id=USER_ID) if not c.get("message_sent")]
        if not contacts:
            return "No pending follow-up was found."
        mark_message_sent(contacts[0]["id"], platform="manual", user_id=USER_ID)
        return f"Marked {contacts[0].get('name')} as followed up."

    if kind == "save_private_info":
        count = save_private_info_updates(USER_ID, action.get("fields", {}))
        return f"Saved {count} private field(s).\n\n{format_vault_summary(USER_ID)}"

    if kind == "draft_application":
        draft = draft_application(USER_ID, action.get("request") or original_text)
        return format_application_draft(draft)

    if kind == "stats":
        return format_networking_stats(user_id=USER_ID)

    if kind == "calendar_help":
        duration = resolve_duration(original_text)
        return (
            "I can help schedule this, but the custom dashboard calendar connector is not enabled yet.\n\n"
            f"I understood this as a calendar task. Estimated duration: {duration} minutes.\n\n"
            "For live Google/Microsoft Calendar writes, use the Chainlit prototype while we wire this UI to the calendar OAuth flow."
        )

    return intro_message()


def intro_message() -> str:
    return (
        "I can help you run entrepreneur workflows from plain language.\n\n"
        "Try messages like:\n"
        "- I met Rahul Sharma at Voko Run. He is a fintech founder at PayNow.\n"
        "- Send Rahul a follow-up message\n"
        "- Show contacts from Voko Run\n"
        "- Draft an application for a startup grant with fields: name, email, LinkedIn, startup name\n"
        "- Save startup_name=Acme Labs | city=Chennai\n\n"
        "Calendar scheduling is planned for this custom UI next; the current Chainlit prototype already supports Google and Microsoft Calendar."
    )

