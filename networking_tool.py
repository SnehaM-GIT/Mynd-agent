"""
networking_tool.py  — Advanced Edition
────────────────────────────────────────────────────────────────────────────────
Full networking intelligence for Mynd:

  ✅ Contact storage with rich metadata
  ✅ Smart follow-up scoring (how hot is this lead?)
  ✅ LLM-powered personalised message generation (Groq)
  ✅ Multi-platform message variants (WhatsApp / LinkedIn / Email)
  ✅ Event-level analytics (who did I meet at X?)
  ✅ Follow-up reminders (contacts not followed up after N days)
  ✅ Conversation notes per contact (multiple touchpoints)
  ✅ Regex + LLM-assisted field extraction fallback
  ✅ Profile system (your bio auto-injected into every message)
────────────────────────────────────────────────────────────────────────────────
"""

import os
import json
import datetime
import re
import storage_tool

# ── Storage ────────────────────────────────────────────────────────────────────
CONTACTS_DIR = "contacts"
PROFILES_DIR = os.path.join(CONTACTS_DIR, "profiles")
os.makedirs(CONTACTS_DIR, exist_ok=True)
os.makedirs(PROFILES_DIR, exist_ok=True)
CONTACTS_FILE = os.path.join(CONTACTS_DIR, "contacts.json")
PROFILE_FILE  = os.path.join(CONTACTS_DIR, "my_profile.json")  # Legacy global
DEFAULT_USER_ID = "default"


# ── EMPTY PROFILE TEMPLATE (Users must fill this) ─────────────────────────────
EMPTY_PROFILE = {
    "name":       "",
    "email":      "",
    "phone":      "",
    "university": "",
    "domains":    "",
    "org":        "",
    "linkedin":   "",
    "instagram":  "",
    "tagline":    "",
    "setup_complete": False
}


# ── Profile helpers - Per-user ────────────────────────────────────────────────

def get_user_profile_path(user_id: str) -> str:
    """Get per-user profile file path"""
    return os.path.join(PROFILES_DIR, f"profile_{user_id}.json")


def load_user_profile(user_id: str) -> dict:
    """Load user's personal profile. Returns empty if not set up yet."""
    stored_profile = storage_tool.load_profile(user_id)
    if stored_profile:
        return stored_profile

    profile_path = get_user_profile_path(user_id)
    if os.path.exists(profile_path):
        with open(profile_path) as f:
            profile = json.load(f)
            storage_tool.save_profile(user_id, profile)
            return profile

    # Legacy global profile is imported only for the compatibility user.
    if user_id == DEFAULT_USER_ID and os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE) as f:
            global_profile = json.load(f)
            # Migrate to per-user
            save_user_profile(user_id, global_profile)
            return global_profile

    return EMPTY_PROFILE.copy()


def save_user_profile(user_id: str, profile: dict):
    """Save user's personal profile"""
    storage_tool.save_profile(user_id, profile)


def is_profile_setup(user_id: str) -> bool:
    """Check if user has completed profile setup"""
    profile = load_user_profile(user_id)
    # Profile is setup if name and at least one social is provided
    return bool(profile.get("name")) and bool(
        profile.get("linkedin") or profile.get("instagram") or profile.get("email")
    )


def profile_setup_status(user_id: str) -> dict:
    """Get profile completeness status"""
    profile = load_user_profile(user_id)
    required_fields = ["name", "linkedin", "instagram"]
    missing = [f for f in required_fields if not profile.get(f)]
    return {
        "complete": len(missing) == 0,
        "missing": missing,
        "profile": profile
    }


def load_profile() -> dict:
    """Legacy function for backward compatibility"""
    stored_profile = storage_tool.load_profile(DEFAULT_USER_ID)
    if stored_profile:
        return stored_profile

    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE) as f:
            profile = json.load(f)
            storage_tool.save_profile(DEFAULT_USER_ID, profile)
            return profile
    return EMPTY_PROFILE.copy()


def save_profile(profile: dict):
    """Legacy function - save global profile"""
    storage_tool.save_profile(DEFAULT_USER_ID, profile)


def update_profile_field(key: str, value: str, user_id: str = None) -> dict:
    """Update a profile field. If user_id provided, updates user profile; else global"""
    if user_id:
        profile = load_user_profile(user_id)
        profile[key] = value
        save_user_profile(user_id, profile)
    else:
        profile = load_profile()
        profile[key] = value
        save_profile(profile)
    return profile


def format_profile_card(profile: dict) -> str:
    p = profile
    has_data = any([p.get('name'), p.get('email'), p.get('linkedin')])

    if not has_data:
        return "❌ **Profile not set up yet!** Say `/profile` to add your details."

    lines = [f"👤 **{p.get('name', '—')}**"]
    if p.get('email'):     lines.append(f"📧 {p['email']}")
    if p.get('phone'):     lines.append(f"📱 {p['phone']}")
    if p.get('university'): lines.append(f"🎓 {p['university']}")
    if p.get('domains'):   lines.append(f"🔬 {p['domains']}")
    if p.get('org'):       lines.append(f"🏢 {p['org']}")
    if p.get('linkedin'):  lines.append(f"🔗 LinkedIn: {p['linkedin']}")
    if p.get('instagram'): lines.append(f"📸 Instagram: {p['instagram']}")
    if p.get('tagline'):   lines.append(f"💬 _{p['tagline']}_")

    return "\n".join(lines)


# ── Contact storage ────────────────────────────────────────────────────────────

def load_contacts(user_id: str = DEFAULT_USER_ID) -> list:
    contacts = storage_tool.load_contacts(user_id)
    if contacts:
        return contacts

    if user_id == DEFAULT_USER_ID and os.path.exists(CONTACTS_FILE):
        with open(CONTACTS_FILE) as f:
            legacy_contacts = json.load(f)
        storage_tool.save_contacts(user_id, legacy_contacts)
        return legacy_contacts
    return []


def import_legacy_data(user_id: str) -> dict:
    imported_profile = False
    imported_contacts = 0

    if os.path.exists(PROFILE_FILE):
        with open(PROFILE_FILE) as f:
            save_user_profile(user_id, json.load(f))
            imported_profile = True

    if os.path.exists(CONTACTS_FILE):
        with open(CONTACTS_FILE) as f:
            contacts = json.load(f)
        for contact in contacts:
            add_contact(contact.copy(), user_id=user_id)
        imported_contacts = len(contacts)

    return {
        "profile": imported_profile,
        "contacts": imported_contacts,
    }


def save_contacts(contacts: list, user_id: str = DEFAULT_USER_ID):
    storage_tool.save_contacts(user_id, contacts)


def _next_id(contacts: list, user_id: str = DEFAULT_USER_ID) -> str:
    return storage_tool.next_contact_id(user_id)


def add_contact(contact_data: dict, user_id: str = DEFAULT_USER_ID) -> dict:
    """
    Save a new contact or update existing (matched by name + event).
    Auto-computes follow-up score on save.
    """
    contacts = load_contacts(user_id)
    name  = contact_data.get("name", "").strip().lower()
    event = contact_data.get("event", "").strip().lower()

    for i, c in enumerate(contacts):
        if (c.get("name", "").lower() == name
                and c.get("event", "").lower() == event):
            contacts[i].update(contact_data)
            contacts[i]["updated_at"] = datetime.datetime.now().isoformat()
            contacts[i]["score"] = _compute_score(contacts[i])
            save_contacts(contacts, user_id)
            return contacts[i]

    contact_data["id"]            = _next_id(contacts, user_id)
    contact_data["saved_at"]      = datetime.datetime.now().isoformat()
    contact_data["message_sent"]  = False
    contact_data["touchpoints"]   = []          # list of follow-up notes
    contact_data["score"]         = _compute_score(contact_data)
    contacts.append(contact_data)
    save_contacts(contacts, user_id)
    return contact_data


def add_touchpoint(contact_id: str, note: str, user_id: str = DEFAULT_USER_ID):
    """Log a new interaction with a contact (call, reply, meeting etc.)"""
    contacts = load_contacts(user_id)
    for c in contacts:
        if c.get("id") == contact_id:
            if "touchpoints" not in c:
                c["touchpoints"] = []
            c["touchpoints"].append({
                "note": note,
                "at": datetime.datetime.now().isoformat()
            })
            c["score"] = _compute_score(c)
            save_contacts(contacts, user_id)
            return c
    return None


def search_contacts(keyword: str, user_id: str = DEFAULT_USER_ID) -> list:
    """Full-text search across all contact fields."""
    contacts = load_contacts(user_id)
    kw = keyword.lower()
    return [
        c for c in contacts
        if kw in " ".join([
            str(c.get(f, ""))
            for f in ["name", "company", "event", "role", "notes", "email", "phone"]
        ]).lower()
    ]


def get_all_contacts(user_id: str = DEFAULT_USER_ID) -> list:
    return load_contacts(user_id)


def get_contacts_by_event(event_name: str, user_id: str = DEFAULT_USER_ID) -> list:
    contacts = load_contacts(user_id)
    ev = event_name.lower()
    return [c for c in contacts if ev in c.get("event", "").lower()]


def get_unsent_contacts(days_threshold: int = 3, user_id: str = DEFAULT_USER_ID) -> list:
    """
    Return contacts where message_sent is False AND
    they were saved more than `days_threshold` days ago.
    These are the 'forgotten' leads.
    """
    contacts = load_contacts(user_id)
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days_threshold)
    results = []
    for c in contacts:
        if not c.get("message_sent"):
            saved = c.get("saved_at", "")
            try:
                saved_dt = datetime.datetime.fromisoformat(saved)
                if saved_dt < cutoff:
                    results.append(c)
            except Exception:
                results.append(c)
    return results


def mark_message_sent(contact_id: str, platform: str = "whatsapp", user_id: str = DEFAULT_USER_ID):
    contacts = load_contacts(user_id)
    for c in contacts:
        if c.get("id") == contact_id:
            c["message_sent"]    = True
            c["message_sent_at"] = datetime.datetime.now().isoformat()
            c["message_platform"] = platform
            c["score"]           = _compute_score(c)
    save_contacts(contacts, user_id)


# ── Follow-up scoring ──────────────────────────────────────────────────────────

def _compute_score(contact: dict) -> int:
    """
    Score a contact 0–100 on 'follow-up priority'.

    Points given for:
      +30  has phone number
      +20  has email
      +15  has LinkedIn
      +10  has notes / conversation context
      +10  has company name
      +15  message NOT yet sent (pending follow-up)
      -20  message already sent (deprioritise)
      +10  multiple touchpoints (active relationship)
      -15  saved > 7 days ago and still unsent (stale)
    """
    score = 0
    if contact.get("phone"):    score += 30
    if contact.get("email"):    score += 20
    if contact.get("linkedin"): score += 15
    if contact.get("notes"):    score += 10
    if contact.get("company"):  score += 10

    if not contact.get("message_sent"):
        score += 15
    else:
        score -= 20

    if len(contact.get("touchpoints", [])) > 0:
        score += 10

    # Stale penalty
    saved = contact.get("saved_at", "")
    try:
        saved_dt = datetime.datetime.fromisoformat(saved)
        days_old = (datetime.datetime.now() - saved_dt).days
        if days_old > 7 and not contact.get("message_sent"):
            score -= 15
    except Exception:
        pass

    return max(0, min(100, score))


def get_priority_contacts(top_n: int = 5, user_id: str = DEFAULT_USER_ID) -> list:
    """Return top N contacts sorted by follow-up score descending."""
    contacts = load_contacts(user_id)
    for c in contacts:
        c["score"] = _compute_score(c)
    return sorted(contacts, key=lambda x: x.get("score", 0), reverse=True)[:top_n]


# ── LLM helpers ────────────────────────────────────────────────────────────────

def _get_groq_client():
    """Get Groq client for LLM calls. Returns None if unavailable."""
    try:
        from groq import Groq
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return None
        return Groq(api_key=api_key)
    except ImportError:
        return None


def _generate_llm_message(contact, profile, event_name="", custom_note="",
                          platform="whatsapp", tone="professional"):
    """Use Groq LLM to generate a truly personalized follow-up message.
    Returns None on failure so callers can fall back to templates."""
    client = _get_groq_client()
    if not client:
        return None

    first = (contact.get("name") or "there").split()[0]
    event = event_name or contact.get("event", "a networking event")
    notes = custom_note or contact.get("notes", "")

    sender_lines = []
    for k, label in [("name", "Name"), ("university", "Affiliation"),
                     ("domains", "Domains"), ("org", "Organization"),
                     ("tagline", "Tagline")]:
        if profile.get(k):
            sender_lines.append(f"{label}: {profile[k]}")

    link_lines = []
    if profile.get("linkedin"):
        link_lines.append(f"LinkedIn: {profile['linkedin']}")
    if profile.get("instagram"):
        link_lines.append(f"Instagram: {profile['instagram']}")

    recip_lines = [f"Name: {contact.get('name', 'Unknown')}"]
    for k, label in [("role", "Role"), ("company", "Company")]:
        if contact.get(k):
            recip_lines.append(f"{label}: {contact[k]}")
    recip_lines.append(f"Met at: {event}")
    if notes:
        recip_lines.append(f"Conversation notes: {notes}")

    plat_hint = {
        "whatsapp": "Casual, warm, under 120 words.",
        "linkedin": "Professional, under 180 words. End with name.",
        "email": "SUBJECT: line first, then body. Under 250 words.",
    }
    tone_hint = {
        "casual": "Friendly and relaxed.",
        "professional": "Polished but warm.",
        "investor": "Value-focused.",
        "sales": "Solution-oriented.",
    }

    prompt = (
        "Write a networking follow-up message.\n\n"
        "SENDER:\n" + "\n".join(sender_lines or ["No details."]) + "\n\n"
        "SOCIAL LINKS (include at end):\n" + "\n".join(link_lines or ["None."]) + "\n\n"
        "RECIPIENT:\n" + "\n".join(recip_lines) + "\n\n"
        f"PLATFORM: {platform} — {plat_hint.get(platform, plat_hint['whatsapp'])}\n"
        f"TONE: {tone} — {tone_hint.get(tone, tone_hint['professional'])}\n\n"
        "RULES:\n"
        f"- Reference SPECIFIC details from conversation notes\n"
        f"- Address by first name ({first}) only\n"
        "- Sound genuinely human, never templated\n"
        "- Include social links at end as 'Let's stay connected:'\n"
        "- Do NOT invent facts or use [brackets]\n"
        "- End with a natural call-to-action"
    )

    try:
        resp = client.chat.completions.create(
            model=os.getenv("MYND_LLM_MODEL", "llama-3.3-70b-versatile"),
            max_tokens=400,
            temperature=0.7,
            messages=[
                {"role": "system", "content":
                 "You write warm, personalized networking follow-up messages. "
                 "Every message feels uniquely crafted. Never generic templates."},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


# ── Message generation (LLM-first, template fallback) ─────────────────────────

def generate_followup_message(
    contact: dict,
    event_name: str = "",
    custom_note: str = "",
    platform: str = "whatsapp",
    user_id: str = None,
    tone: str = "professional",
) -> tuple:
    """
    Generate a personalised follow-up message.

    Tries LLM generation first for dynamic, context-aware messages.
    Falls back to templates if LLM is unavailable or fails.

    Returns: (message, profile_complete, missing_fields)
    """
    # Load USER'S actual profile
    profile = load_user_profile(user_id) if user_id else load_profile()

    # Check if profile is complete
    profile_complete = bool(profile.get("name")) and bool(
        profile.get("linkedin") or profile.get("instagram")
    )

    missing_fields = []
    if not profile.get("name"):
        missing_fields.append("name")
    if not profile.get("linkedin"):
        missing_fields.append("LinkedIn profile")
    if not profile.get("instagram"):
        missing_fields.append("Instagram profile")

    if not profile_complete:
        error_msg = (
            f"⚠️ **Can't generate follow-up message yet**\n\n"
            f"I need your info first to personalize messages. Missing:\n"
            + "\n".join([f"  • {f}" for f in missing_fields]) +
            f"\n\nSay `/profile` to set up your details."
        )
        return (error_msg, False, missing_fields)

    # ── Try LLM-powered generation first ──────────────────────────────────────
    llm_msg = _generate_llm_message(
        contact=contact,
        profile=profile,
        event_name=event_name or contact.get("event", ""),
        custom_note=custom_note,
        platform=platform,
        tone=tone,
    )
    if llm_msg:
        return (llm_msg, True, [])

    # ── Fallback to template generation ───────────────────────────────────────
    name      = contact.get("name", "there")
    first     = name.split()[0] if name else "there"
    event     = event_name or contact.get("event", "the event")
    role      = contact.get("role", "")
    company   = contact.get("company", "")
    notes     = custom_note or contact.get("notes", "")

    # Build opening line
    if notes:
        opening = f"Great meeting you at {event} today — {notes}."
    elif role and company:
        opening = (
            f"Great meeting you at {event} today — "
            f"really enjoyed hearing about your work as {role} at {company}."
        )
    elif company:
        opening = f"Great meeting you at {event} today — loved connecting with the {company} team."
    else:
        opening = f"Great meeting you at {event} today — really enjoyed our conversation."

    # Build user intro from their actual data
    profile_intro_parts = []
    if profile.get("name"):
        profile_intro_parts.append(f"I'm {profile['name']}")
    if profile.get("university"):
        profile_intro_parts.append(f"from {profile['university']}")
    if profile.get("domains"):
        profile_intro_parts.append(f"I work with startups in {profile['domains']}")
    if profile.get("org"):
        profile_intro_parts.append(f"and have exposure to {profile['org']}")

    my_intro = " ".join(profile_intro_parts) if profile_intro_parts else "I'd love to connect and explore opportunities."
    my_value = profile.get("tagline", "I'm always keen to collaborate with ambitious founders!")

    # ── WhatsApp style ─────────────────────────────────────────────────────────
    if platform == "whatsapp":
        message = f"Hey {first},\n\n{opening}\n\n{my_intro}.\n\n{my_value}\n\n"
        if profile.get("linkedin") or profile.get("instagram"):
            message += "Let's stay connected:\n"
            if profile.get("linkedin"):
                message += f"🔗 LinkedIn: {profile['linkedin']}\n"
            if profile.get("instagram"):
                message += f"📸 Instagram: {profile['instagram']}"
        return (message, True, [])

    # ── LinkedIn style ─────────────────────────────────────────────────────────
    elif platform == "linkedin":
        message = (
            f"Hi {first},\n\n"
            f"It was great connecting with you at {event}. "
            f"{opening.replace('Great meeting you at ' + event + ' today — ', '')}\n\n"
            f"{my_intro}.\n\n"
            f"{my_value}\n\n"
            f"Would love to stay in touch and explore collaboration opportunities. "
            f"Feel free to message me anytime.\n\n"
            f"Best,\n{profile.get('name', 'Mynd')}"
        )
        return (message, True, [])

    # ── Email style ────────────────────────────────────────────────────────────
    elif platform == "email":
        subject = f"Great meeting you at {event} — {profile.get('name', 'Mynd')}"
        body = (
            f"Hi {first},\n\n"
            f"{opening}\n\n"
            f"{my_intro}.\n\n"
            f"{my_value}\n\n"
            f"I'd love to schedule a quick call to explore collaboration. "
            f"Let me know what works for you.\n\n"
            f"Best regards,\n"
            f"{profile.get('name', 'Mynd')}\n"
        )
        if profile.get("email"):
            body += f"Email: {profile['email']}\n"
        if profile.get("linkedin"):
            body += f"LinkedIn: {profile['linkedin']}\n"
        return (f"SUBJECT: {subject}\n\n{body}", True, [])

    # Fallback to the default WhatsApp style.
    return generate_followup_message(
        contact, event_name, custom_note, "whatsapp", user_id, tone
    )


# ── Analytics ──────────────────────────────────────────────────────────────────

def get_networking_stats(user_id: str = DEFAULT_USER_ID) -> dict:
    contacts = load_contacts(user_id)
    total    = len(contacts)
    sent     = sum(1 for c in contacts if c.get("message_sent"))
    unsent   = total - sent
    events   = {}
    for c in contacts:
        e = c.get("event", "Unknown")
        events[e] = events.get(e, 0) + 1
    top_event = max(events, key=events.get) if events else "—"

    return {
        "total":     total,
        "sent":      sent,
        "unsent":    unsent,
        "events":    events,
        "top_event": top_event,
    }


def format_networking_stats(user_id: str = DEFAULT_USER_ID) -> str:
    s = get_networking_stats(user_id)
    if s["total"] == 0:
        return "📭 No contacts saved yet. Start by telling me who you met!"

    event_lines = "\n".join(
        f"  • {e}: {n} contact(s)" for e, n in s["events"].items()
    )
    rate = int((s["sent"] / s["total"]) * 100) if s["total"] else 0
    bar_filled = int(rate / 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    return (
        f"📊 **Networking Stats**\n\n"
        f"👥 Total contacts: **{s['total']}**\n"
        f"✅ Follow-ups sent: **{s['sent']}**\n"
        f"⏳ Pending follow-ups: **{s['unsent']}**\n"
        f"📈 Follow-up rate: `{bar}` {rate}%\n\n"
        f"📍 **By event:**\n{event_lines}\n\n"
        f"🏆 Most active event: **{s['top_event']}**"
    )


def format_contact_card(contact: dict, show_score: bool = True) -> str:
    lines = [f"👤 **{contact.get('name', 'Unknown')}**"]

    if contact.get("role"):    lines.append(f"💼 {contact['role']}")
    if contact.get("company"): lines.append(f"🏢 {contact['company']}")
    if contact.get("event"):   lines.append(f"📍 Met at: {contact['event']}")
    if contact.get("phone"):   lines.append(f"📱 {contact['phone']}")
    if contact.get("email"):   lines.append(f"📧 {contact['email']}")
    if contact.get("linkedin"):lines.append(f"🔗 {contact['linkedin']}")
    if contact.get("notes"):   lines.append(f"📝 {contact['notes']}")

    touchpoints = contact.get("touchpoints", [])
    if touchpoints:
        lines.append(f"🤝 {len(touchpoints)} follow-up(s) logged")

    if contact.get("message_sent"):
        sent_at  = contact.get("message_sent_at", "")[:10]
        platform = contact.get("message_platform", "")
        lines.append(f"✅ Sent via {platform}" + (f" on {sent_at}" if sent_at else ""))
    else:
        lines.append("⏳ Follow-up pending")

    if show_score:
        score = contact.get("score", _compute_score(contact))
        bar   = "🟢" if score >= 70 else "🟡" if score >= 40 else "🔴"
        lines.append(f"{bar} Priority score: {score}/100")

    lines.append(f"🆔 `{contact.get('id', '')}`")
    return "\n".join(lines)


def format_contacts_list(contacts: list, show_score: bool = True) -> str:
    if not contacts:
        return "📭 No contacts found."
    out = f"📋 **{len(contacts)} contact(s):**\n\n"
    for c in sorted(contacts, key=lambda x: x.get("score", 0), reverse=True):
        out += format_contact_card(c, show_score=show_score) + "\n\n---\n\n"
    return out.strip()


# ── Text extraction helpers ────────────────────────────────────────────────────

def extract_contact_from_text(raw: str) -> dict:
    contact = {}
    email = re.search(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', raw)
    if email: contact["email"] = email.group()

    phone = re.search(r'(?:\+91[\s-]?)?[6-9]\d{9}|0\d{10}', raw)
    if phone: contact["phone"] = phone.group()

    linkedin = re.search(r'linkedin\.com/in/[\w\-]+', raw, re.I)
    if linkedin: contact["linkedin"] = "https://" + linkedin.group()

    insta = re.search(r'instagram\.com/([\w.]+)|(?<![\w.])@([\w.]+)', raw, re.I)
    if insta: contact["instagram"] = "@" + (insta.group(1) or insta.group(2))

    return contact
