import os
import csv
import io
import re
from urllib.parse import quote
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.responses import StreamingResponse
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
from calendar_tool import (
    check_conflicts,
    create_all_day_calendar_event,
    create_calendar_event,
    delete_calendar_event,
    get_events,
    resolve_duration,
)

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
    avatar_url: str = ""


class ChatPayload(BaseModel):
    message: str


class ContactPayload(BaseModel):
    name: str = ""
    role: str = ""
    company: str = ""
    event: str = ""
    phone: str = ""
    email: str = ""
    linkedin: str = ""
    notes: str = ""


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
    errors = validate_profile(profile)
    if errors:
        raise HTTPException(status_code=400, detail=" ".join(errors))
    profile["setup_complete"] = is_complete_profile(profile)
    save_user_profile(USER_ID, profile)
    profile["completion"] = profile_completion(profile)
    profile["user_id"] = USER_ID
    return profile


@app.post("/api/profile/photo")
async def upload_profile_photo(file: UploadFile = File(...)):
    suffix = Path(file.filename or "profile.png").suffix.lower()
    if suffix not in [".png", ".jpg", ".jpeg", ".webp"]:
        raise HTTPException(status_code=400, detail="Upload a PNG, JPG, or WEBP image.")
    upload_dir = APP_DIR / "static" / "uploads"
    upload_dir.mkdir(exist_ok=True)
    path = upload_dir / f"profile_{USER_ID}{suffix}"
    path.write_bytes(await file.read())
    profile = load_user_profile(USER_ID)
    profile["avatar_url"] = f"/static/uploads/{path.name}"
    save_user_profile(USER_ID, profile)
    return {"avatar_url": profile["avatar_url"]}


@app.get("/api/contacts")
def contacts():
    return {"contacts": get_all_contacts(user_id=USER_ID)}


@app.post("/api/contacts/preview")
def preview_contact(payload: ChatPayload):
    contact = parse_contact(payload.message)
    if not contact:
        contact = extract_contact_from_text(payload.message)
        contact["notes"] = payload.message
    duplicate = find_duplicate_contact(contact)
    return {"contact": contact, "duplicate": duplicate}


@app.post("/api/contacts")
def save_contact_api(payload: ContactPayload):
    data = payload.model_dump()
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="Contact name is required.")
    duplicate = find_duplicate_contact(data)
    saved = add_contact(data, user_id=USER_ID)
    return {
        "contact": saved,
        "merged": bool(duplicate),
        "message": "Merged with an existing contact." if duplicate else "Contact saved.",
    }


@app.get("/api/contacts/export")
def export_contacts():
    output = io.StringIO()
    fields = ["id", "name", "role", "company", "event", "phone", "email", "linkedin", "notes", "message_sent"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(get_all_contacts(user_id=USER_ID))
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=mynd_contacts.csv"},
    )


@app.post("/api/contacts/import")
async def import_contacts(file: UploadFile = File(...)):
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))
    imported = 0
    for row in reader:
        if row.get("name"):
            add_contact(dict(row), user_id=USER_ID)
            imported += 1
    return {"imported": imported}


@app.post("/api/business-card")
async def business_card(file: UploadFile = File(...)):
    content = await file.read()
    mime = file.content_type or "image/jpeg"
    try:
        from groq import Groq
        import base64

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not configured.")
        b64 = base64.b64encode(content).decode("utf-8")
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("MYND_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                    {"type": "text", "text": "Extract this business card as JSON with keys: name, role, company, phone, email, linkedin, website, address. Empty string for missing fields."},
                ],
            }],
        )
        raw = response.choices[0].message.content.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        contact = {}
        if start >= 0 and end > start:
            import json
            contact = json.loads(raw[start:end])
        contact["notes"] = "Imported from business card."
        return {"contact": contact, "needs_manual_review": True}
    except Exception as exc:
        return {
            "contact": {"notes": f"Business card upload received, but OCR needs manual review. Reason: {exc}"},
            "needs_manual_review": True,
        }


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


def validate_profile(profile: dict) -> list[str]:
    errors = []
    email = profile.get("email", "").strip()
    phone = profile.get("phone", "").strip()
    linkedin = profile.get("linkedin", "").strip()
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors.append("Enter a valid email.")
    if phone and len(re.sub(r"\D+", "", phone)) < 10:
        errors.append("Enter a valid phone number.")
    if linkedin and "linkedin.com/" not in linkedin.lower():
        errors.append("Enter a valid LinkedIn URL.")
    return errors


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
        name = followup.group(1).strip(" .")
        name = re.sub(r"\b(?:a|an|the)?\s*(?:casual|professional|investor|sales|whatsapp|linkedin|email|mail)\b", "", name, flags=re.I)
        name = re.sub(r"\s+", " ", name).strip(" .")
        return {
            "action": "send_followup",
            "name": name,
            "channel": extract_channel(lower),
            "tone": extract_tone(lower),
        }

    if "remind" in lower and "follow" in lower:
        match = re.search(r"follow[- ]?up\s+(?:with|to|for)?\s*([a-z][\w .'-]+)", text, re.I)
        return {
            "action": "followup_reminder",
            "name": match.group(1).strip(" .") if match else "",
            "date": extract_date_phrase(text) or "tomorrow",
        }

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

    if any(word in lower for word in ["application", "form", "grant", "apply"]):
        return {"action": "draft_application", "request": text}

    calendar_action = parse_calendar_intent(text)
    if calendar_action:
        return calendar_action

    if any(phrase in lower for phrase in ["networking stats", "follow-up rate", "stats"]):
        return {"action": "stats"}

    if any(phrase in lower for phrase in ["what can you do", "help", "features"]):
        return {"action": "intro"}

    model_action = route_with_model(text)
    if model_action:
        return model_action

    return {"action": "intro"}


def parse_calendar_intent(text: str) -> dict | None:
    lower = text.lower().strip()
    if not any(word in lower for word in ["schedule", "block", "calendar", "calender", "meeting", "event", "birthday", "remind", "delete", "remove", "cancel"]):
        return None

    if (
        any(word in lower for word in ["what", "show", "view", "list"])
        and any(word in lower for word in ["calendar", "calender", "schedule", "events", "have"])
    ):
        date = extract_date_phrase(text) or "today"
        return {"action": "view_calendar", "date": date}

    if any(word in lower for word in ["delete", "remove", "cancel"]):
        date = extract_date_phrase(text) or "today"
        title = extract_title(text, default="event")
        return {"action": "delete_calendar", "title": title, "date": date}

    if any(word in lower for word in ["schedule", "block", "add", "create", "remind", "birthday", "meeting", "event"]):
        date = extract_date_phrase(text)
        time = extract_time_phrase(text)
        title = extract_title(text, default="Event")
        all_day = not time and any(word in lower for word in ["birthday", "anniversary", "holiday", "deadline"])
        if not date:
            return {"action": "calendar_missing_date", "title": title}
        if not time and not all_day:
            return {"action": "calendar_missing_time", "title": title, "date": date}
        return {
            "action": "create_calendar",
            "title": title,
            "date": date,
            "time": time or "",
            "duration": "1 hour",
            "all_day": all_day,
        }
    return None


def extract_date_phrase(text: str) -> str:
    lower = text.lower()
    relative = re.search(r"\b(today|tomorrow|day after tomorrow|next\s+\w+)\b", lower)
    if relative:
        return relative.group(1)

    weekday = re.search(r"\b(?:this\s+|next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower)
    if weekday:
        return weekday.group(0)

    month_names = (
        "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        "jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    )
    month_date = re.search(
        rf"\b(\d{{1,2}})\s*(?:st|nd|rd|th)?\s+(?:{month_names})(?:\s+\d{{4}})?\b",
        lower,
    )
    if month_date:
        return month_date.group(0)

    month_first = re.search(
        rf"\b(?:{month_names})\s+\d{{1,2}}\s*(?:st|nd|rd|th)?(?:\s+\d{{4}})?\b",
        lower,
    )
    if month_first:
        return month_first.group(0)

    numeric = re.search(r"\b\d{1,2}[\/\-.]\d{1,2}(?:[\/\-.]\d{2,4})?\b", lower)
    if numeric:
        return numeric.group(0)
    return ""


def extract_time_phrase(text: str) -> str:
    match = re.search(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b|\b\d{1,2}:\d{2}\b", text, re.I)
    if match:
        return match.group(0)
    named = re.search(r"\b(morning|afternoon|evening|night|noon|midnight)\b", text, re.I)
    return named.group(1) if named else ""


def extract_channel(lower: str) -> str:
    if "linkedin" in lower:
        return "linkedin"
    if "email" in lower or "mail" in lower:
        return "email"
    return "whatsapp"


def extract_tone(lower: str) -> str:
    for tone in ["casual", "professional", "investor", "sales"]:
        if tone in lower:
            return tone
    return "professional"


def extract_title(text: str, default: str = "Event") -> str:
    cleaned = re.sub(r"\bon\s+my\s+(?:google|microsoft|outlook)?\s*calend[ae]r\b", "", text, flags=re.I)
    cleaned = re.sub(r"\b(?:google|microsoft|outlook)\s+calend[ae]r\b", "", cleaned, flags=re.I)
    title_match = re.search(r"\b(?:as|for)\s+(.+)$", cleaned, re.I)
    if title_match:
        title = title_match.group(1)
    else:
        title = cleaned
    title = re.sub(r"\b(?:schedule|block|add|create|remind me|remind)\b", "", title, flags=re.I)
    title = re.sub(r"\b(?:delete|remove|cancel)\b", "", title, flags=re.I)
    date = extract_date_phrase(title)
    if date:
        title = re.sub(re.escape(date), "", title, flags=re.I)
    time = extract_time_phrase(title)
    if time:
        title = title.replace(time, "")
    title = re.sub(r"\b(?:on|at)\s*$", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip(" .,-")
    return title or default


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


def find_duplicate_contact(contact: dict) -> dict | None:
    name = (contact.get("name") or "").strip().lower()
    email = (contact.get("email") or "").strip().lower()
    phone = re.sub(r"\D+", "", contact.get("phone") or "")
    for existing in get_all_contacts(user_id=USER_ID):
        existing_phone = re.sub(r"\D+", "", existing.get("phone") or "")
        if email and email == (existing.get("email") or "").strip().lower():
            return existing
        if phone and phone == existing_phone:
            return existing
        if name and name == (existing.get("name") or "").strip().lower():
            return existing
    return None


def build_followup(contact: dict, channel: str, tone: str) -> tuple[str, str]:
    """Generate follow-up message using shared LLM function + build send link."""
    msg, complete, missing = generate_followup_message(
        contact=contact,
        event_name=contact.get("event", ""),
        custom_note="",
        platform=channel,
        user_id=USER_ID,
        tone=tone,
    )
    if not complete:
        return (msg, "")

    # Build send link (WhatsApp deep link or mailto)
    link = ""
    if channel == "whatsapp" and contact.get("phone"):
        phone = re.sub(r"\D+", "", contact["phone"])
        if len(phone) == 10:
            phone = "91" + phone
        link = f"https://wa.me/{phone}?text={quote(msg)}"
    elif channel == "email" and contact.get("email"):
        subject = f"Great meeting you at {contact.get('event', 'the event')}"
        link = f"mailto:{contact['email']}?subject={quote(subject)}&body={quote(msg)}"

    return (msg, link)


def clean_contact_context(notes: str) -> str:
    text = str(notes or "")
    text = re.sub(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', '', text)
    text = re.sub(r'(?:\+91[\s-]?)?[6-9]\d{9}|0\d{10}', '', text)
    text = re.sub(r'https?://\S+|linkedin\.com/\S+|instagram\.com/\S+', '', text, flags=re.I)
    text = re.sub(r"\bI met\s+[A-Z][\w.'-]*(?:\s+[A-Z][\w.'-]*){0,3}\s+at\s+[^.]+\.?", "", text)
    text = re.sub(r"\b(?:his|her|their)\s+(?:email|phone|number)\s+(?:is\s+)?", "", text, flags=re.I)
    text = re.sub(r"\bwe\s+discussed\s+", "", text, flags=re.I)
    text = re.sub(r"\bdiscussed\s+", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" .,-")
    return text[:180]


def build_profile_intro(profile: dict) -> str:
    first = f"I'm {profile.get('name')}"
    if profile.get("university"):
        first += f" from {profile['university']}"
    parts = [first]
    if profile.get("domains"):
        parts.append(f"I work around {profile['domains']}")
    if profile.get("org"):
        parts.append(f"I am also connected with {profile['org']}")
    return ". ".join(parts)


def handle_action(action: dict, original_text: str) -> str:
    kind = action.get("action")

    if kind == "save_contact":
        duplicate = find_duplicate_contact(action)
        saved = add_contact(action, user_id=USER_ID)
        prefix = "Updated existing contact.\n\n" if duplicate else "Contact saved.\n\n"
        return (
            prefix +
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
        channel = action.get("channel", "whatsapp")
        tone = action.get("tone", "professional")
        message, link = build_followup(contact, channel, tone)
        link_text = f"\n\nOpen draft: {link}" if link else ""
        return f"Here is a {tone} {channel} follow-up for {contact.get('name')}:\n\n{message}{link_text}"

    if kind == "followup_reminder":
        matches = search_contacts(action.get("name", ""), user_id=USER_ID)
        title = f"Follow up with {matches[0].get('name')}" if matches else "Follow-up reminder"
        try:
            return create_calendar_event(USER_ID, title, action.get("date", "tomorrow"), "9am", duration_minutes=15)
        except Exception as exc:
            return calendar_error_message(exc)

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
        return format_application_draft(draft).replace(
            "Add missing details with `/vault set field=value` and ask me to draft again.",
            "Save the missing details from chat, for example: save startup_name=Acme Labs | city=Chennai. Then ask me to draft again.",
        )

    if kind == "stats":
        return format_networking_stats(user_id=USER_ID)

    if kind == "view_calendar":
        try:
            return get_events(USER_ID, action.get("date", "today"))
        except Exception as exc:
            return calendar_error_message(exc)

    if kind == "delete_calendar":
        try:
            return delete_calendar_event(
                USER_ID,
                action.get("title", "event"),
                action.get("date", "today"),
            )
        except Exception as exc:
            return calendar_error_message(exc)

    if kind == "create_calendar":
        try:
            if action.get("all_day"):
                return create_all_day_calendar_event(
                    USER_ID,
                    action.get("title", "Event"),
                    action.get("date", "today"),
                )

            duration = resolve_duration(action.get("duration", "1 hour"))
            conflicts = check_conflicts(
                USER_ID,
                action.get("date", "today"),
                action.get("time", ""),
                duration,
            )
            if conflicts:
                conflict_list = "\n".join(
                    f"- {item.get('summary', 'Untitled')}" for item in conflicts
                )
                return (
                    "I found another event at that time, so I did not create a duplicate.\n\n"
                    f"{conflict_list}\n\n"
                    "Try another time, or tell me clearly that you want to create it anyway."
                )
            return create_calendar_event(
                USER_ID,
                action.get("title", "Event"),
                action.get("date", "today"),
                action.get("time", ""),
                duration_minutes=duration,
            )
        except Exception as exc:
            return calendar_error_message(exc)

    if kind == "calendar_missing_time":
        return (
            f"I can schedule {action.get('title', 'that')}, but I need a time.\n\n"
            f"Try: Schedule {action.get('title', 'it')} on {action.get('date', 'that date')} at 4pm."
        )

    if kind == "calendar_missing_date":
        return (
            f"I can schedule {action.get('title', 'that')}, but I need a date.\n\n"
            "Try: Block 14 May 2026 as Sowmya's birthday."
        )

    return intro_message()


def calendar_error_message(exc: Exception) -> str:
    text = str(exc)
    if "credentials.json" in text:
        return "Google Calendar is not configured yet. Add `credentials.json` to the project root, then try again."
    if "access_denied" in text.lower():
        return "Google Calendar access was denied. Please approve calendar access and try again."
    return (
        "I understood the calendar task, but Google Calendar returned an error.\n\n"
        f"{text}\n\n"
        "If this is your first calendar action, a Google sign-in window may need to be completed."
    )


def intro_message() -> str:
    return (
        "I can help you run entrepreneur workflows from plain language.\n\n"
        "Try messages like:\n"
        "- I met Rahul Sharma at Voko Run. He is a fintech founder at PayNow.\n"
        "- Send Rahul a follow-up message\n"
        "- Show contacts from Voko Run\n"
        "- Block 14 May 2026 as Sowmya's birthday on my Google Calendar\n"
        "- What do I have on Friday?\n"
        "- Draft an application for a startup grant with fields: name, email, LinkedIn, startup name\n"
        "- Save startup_name=Acme Labs | city=Chennai\n\n"
        "For calendar actions, Mynd may open Google sign-in the first time so it can connect your calendar."
    )
