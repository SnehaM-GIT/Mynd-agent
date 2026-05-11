import datetime
import re
from collections import defaultdict

import storage_tool
from networking_tool import load_user_profile


SENSITIVE_HINTS = {
    "aadhaar", "pan", "gst", "bank", "account", "ifsc", "passport",
    "password", "secret", "token", "tax", "address", "dob",
}

FIELD_ALIASES = {
    "name": ["name", "full name", "founder name", "applicant"],
    "email": ["email", "mail"],
    "phone": ["phone", "mobile", "contact number", "whatsapp"],
    "linkedin": ["linkedin", "linked in"],
    "instagram": ["instagram", "social"],
    "university": ["university", "college", "education"],
    "org": ["organization", "organisation", "company", "institution", "affiliation"],
    "domains": ["domain", "sector", "industry", "expertise", "background"],
    "tagline": ["bio", "about", "introduction", "summary", "pitch"],
}


def parse_private_info_updates(text: str) -> dict[str, str]:
    body = re.sub(r"^/vault\s*(set|add|update)?", "", text, flags=re.I).strip()
    if not body:
        return {}

    updates = {}
    parts = re.split(r"\s*\|\s*|\n+", body)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, value = part.split("=", 1)
        elif ":" in part:
            key, value = part.split(":", 1)
        else:
            continue
        key = _normalize_key(key)
        value = value.strip()
        if key and value:
            updates[key] = value
    return updates


def save_private_info_updates(user_id: str, updates: dict[str, str], category: str = "application") -> int:
    saved = 0
    for key, value in updates.items():
        storage_tool.save_private_info(user_id, key, value, _category_for_key(key, category))
        saved += 1
    return saved


def get_private_info(user_id: str) -> dict[str, dict]:
    return storage_tool.load_private_info(user_id)


def format_vault_summary(user_id: str, reveal: bool = False) -> str:
    profile = load_user_profile(user_id)
    info = get_private_info(user_id)

    lines = ["**Private Info Vault**"]
    lines.append("Encrypted local storage: profile, private fields, and application drafts.")

    profile_fields = [
        key for key in ["name", "email", "phone", "university", "domains", "org", "linkedin", "instagram", "tagline"]
        if profile.get(key)
    ]
    lines.append(f"\nProfile fields ready: **{len(profile_fields)}**")
    if profile_fields:
        lines.append(", ".join(profile_fields))

    if not info:
        lines.append(
            "\nNo extra private application fields saved yet.\n\n"
            "Add them like:\n"
            "`/vault set startup_name=Acme Labs | legal_name=Suriya Jayan | city=Chennai`"
        )
        return "\n".join(lines)

    grouped = defaultdict(list)
    for key, item in info.items():
        value = item.get("value", "")
        grouped[item.get("category", "general")].append((key, value))

    lines.append(f"\nExtra vault fields: **{len(info)}**")
    for category in sorted(grouped):
        lines.append(f"\n**{category.title()}**")
        for key, value in sorted(grouped[category]):
            shown = value if reveal else _redact(value, key)
            lines.append(f"- `{key}`: {shown}")

    return "\n".join(lines)


def build_application_context(user_id: str) -> dict[str, str]:
    profile = load_user_profile(user_id)
    context = {}
    for key, value in profile.items():
        if key == "setup_complete" or value in [None, ""]:
            continue
        context[_normalize_key(key)] = str(value)

    for key, item in get_private_info(user_id).items():
        if item.get("value"):
            context[_normalize_key(key)] = str(item["value"])
    return context


def draft_application(user_id: str, request_text: str) -> dict:
    fields = _extract_requested_fields(request_text)
    context = build_application_context(user_id)

    answers = []
    missing = []
    for field in fields:
        value, source = _match_field(field, context)
        if value:
            answers.append({"field": field, "answer": value, "source": source})
        else:
            missing.append(field)

    if not fields:
        for key in sorted(context):
            answers.append({"field": key.replace("_", " "), "answer": context[key], "source": key})

    title = _title_from_request(request_text)
    draft = {
        "title": title,
        "request": request_text,
        "answers": answers,
        "missing": missing,
        "created_for": "application",
        "generated_at": datetime.datetime.now().isoformat(),
    }
    return storage_tool.save_application_draft(user_id, draft)


def format_application_draft(draft: dict) -> str:
    lines = [f"**Application Draft: {draft.get('title', 'Application')}**"]

    answers = draft.get("answers", [])
    missing = draft.get("missing", [])
    if answers:
        lines.append("\n**Suggested answers**")
        for item in answers:
            lines.append(f"- **{item['field']}**: {item['answer']}")
    else:
        lines.append("\nI do not have enough stored information to draft answers yet.")

    if missing:
        lines.append("\n**Missing fields**")
        for field in missing:
            lines.append(f"- {field}")
        lines.append("\nAdd missing details with `/vault set field=value` and ask me to draft again.")

    lines.append(f"\nDraft ID: `{draft.get('id', '')}`")
    return "\n".join(lines)


def format_application_drafts(user_id: str) -> str:
    drafts = storage_tool.load_application_drafts(user_id)
    if not drafts:
        return "No application drafts yet. Ask me to draft an application from your saved profile."

    lines = [f"**{len(drafts)} application draft(s)**"]
    for draft in drafts[:10]:
        created = draft.get("created_at", "")[:10]
        answer_count = len(draft.get("answers", []))
        missing_count = len(draft.get("missing", []))
        lines.append(
            f"- `{draft.get('id')}` {draft.get('title', 'Application')} "
            f"({created}) - {answer_count} answer(s), {missing_count} missing"
        )
    return "\n".join(lines)


def _extract_requested_fields(text: str) -> list[str]:
    quoted = re.findall(r'"([^"]+)"|' r"'([^']+)'", text)
    fields = [a or b for a, b in quoted if (a or b).strip()]

    lower = text.lower()
    marker_match = re.search(r"(fields?|questions?)\s*(are|:|-)\s*(.+)$", lower, re.I | re.S)
    if marker_match:
        fields.extend(_split_fields(marker_match.group(3)))

    if not fields and any(word in lower for word in ["application", "form", "apply"]):
        known = [
            "name", "email", "phone", "linkedin", "instagram",
            "university", "organization", "bio", "domain",
        ]
        fields = [field for field in known if field in lower]

    cleaned = []
    seen = set()
    for field in fields:
        field = field.strip(" .,:;-")
        if field and field not in seen:
            cleaned.append(field)
            seen.add(field)
    return cleaned


def _split_fields(text: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(r",|\||\n| and ", text)
        if item.strip()
    ]


def _match_field(field: str, context: dict[str, str]) -> tuple[str | None, str | None]:
    normalized = _normalize_key(field)
    if normalized in context:
        return context[normalized], normalized

    field_lower = field.lower()
    for key, aliases in FIELD_ALIASES.items():
        if any(alias in field_lower for alias in aliases) and key in context:
            return context[key], key

    field_tokens = set(re.findall(r"[a-z0-9]+", field_lower))
    best_key = None
    best_overlap = 0
    for key in context:
        key_tokens = set(key.split("_"))
        overlap = len(field_tokens & key_tokens)
        if overlap > best_overlap:
            best_key = key
            best_overlap = overlap

    if best_key and best_overlap > 0:
        return context[best_key], best_key
    return None, None


def _title_from_request(text: str) -> str:
    match = re.search(r"(?:for|to)\s+(.+?)(?:\s+fields?\b|\s+questions?\b|[.,\n]|$)", text, re.I)
    if match:
        return match.group(1).strip()[:80]
    return "Application draft"


def _category_for_key(key: str, default: str) -> str:
    if any(hint in key for hint in SENSITIVE_HINTS):
        return "sensitive"
    if any(word in key for word in ["startup", "company", "pitch", "revenue", "team"]):
        return "business"
    return default


def _redact(value: str, key: str) -> str:
    if not value:
        return ""
    if any(hint in key for hint in SENSITIVE_HINTS):
        return "[saved securely]"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * min(8, len(value) - 4)}{value[-2:]}"


def _normalize_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower())
    key = re.sub(r"_+", "_", key).strip("_")
    return key
