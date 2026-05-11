import datetime
import json
import os
import re
import sqlite3
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


DATA_DIR = "data"
DB_PATH = os.path.join(DATA_DIR, "mynd.sqlite")
KEY_PATH = os.path.join(DATA_DIR, ".secret.key")


def ensure_storage():
    os.makedirs(DATA_DIR, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                payload BLOB NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                user_id TEXT NOT NULL,
                contact_id TEXT NOT NULL,
                name_search TEXT NOT NULL DEFAULT '',
                event_search TEXT NOT NULL DEFAULT '',
                company_search TEXT NOT NULL DEFAULT '',
                score INTEGER NOT NULL DEFAULT 0,
                message_sent INTEGER NOT NULL DEFAULT 0,
                payload BLOB NOT NULL,
                saved_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, contact_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_contacts_user_score "
            "ON contacts(user_id, score DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_contacts_user_event "
            "ON contacts(user_id, event_search)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS private_info (
                user_id TEXT NOT NULL,
                info_key TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                payload BLOB NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, info_key)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_private_info_user_category "
            "ON private_info(user_id, category)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS application_drafts (
                user_id TEXT NOT NULL,
                draft_id TEXT NOT NULL,
                title TEXT NOT NULL,
                payload BLOB NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, draft_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_application_drafts_user_updated "
            "ON application_drafts(user_id, updated_at DESC)"
        )


def load_profile(user_id: str) -> dict | None:
    ensure_storage()
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM user_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return _decrypt_json(row["payload"]) if row else None


def save_profile(user_id: str, profile: dict):
    ensure_storage()
    now = _now()
    payload = _encrypt_json(profile)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_profiles(user_id, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (user_id, payload, now),
        )


def load_contacts(user_id: str) -> list[dict]:
    ensure_storage()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT payload FROM contacts WHERE user_id = ? ORDER BY score DESC, saved_at DESC",
            (user_id,),
        ).fetchall()
    return [_decrypt_json(row["payload"]) for row in rows]


def save_contact(user_id: str, contact: dict):
    ensure_storage()
    now = _now()
    saved_at = contact.get("saved_at") or now
    contact["saved_at"] = saved_at
    contact["updated_at"] = now
    payload = _encrypt_json(contact)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO contacts(
                user_id, contact_id, name_search, event_search, company_search,
                score, message_sent, payload, saved_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, contact_id) DO UPDATE SET
                name_search = excluded.name_search,
                event_search = excluded.event_search,
                company_search = excluded.company_search,
                score = excluded.score,
                message_sent = excluded.message_sent,
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                contact["id"],
                _clean(contact.get("name", "")),
                _clean(contact.get("event", "")),
                _clean(contact.get("company", "")),
                int(contact.get("score", 0)),
                1 if contact.get("message_sent") else 0,
                payload,
                saved_at,
                now,
            ),
        )


def save_contacts(user_id: str, contacts: list[dict]):
    for contact in contacts:
        save_contact(user_id, contact)


def load_private_info(user_id: str) -> dict[str, dict]:
    ensure_storage()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT info_key, category, payload, updated_at
            FROM private_info
            WHERE user_id = ?
            ORDER BY category, info_key
            """,
            (user_id,),
        ).fetchall()
    info = {}
    for row in rows:
        payload = _decrypt_json(row["payload"])
        info[row["info_key"]] = {
            "value": payload.get("value", ""),
            "category": row["category"],
            "updated_at": row["updated_at"],
        }
    return info


def save_private_info(user_id: str, info_key: str, value: str, category: str = "general"):
    ensure_storage()
    now = _now()
    clean_key = _clean_key(info_key)
    clean_category = _clean_key(category or "general")
    payload = _encrypt_json({"value": value})
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO private_info(user_id, info_key, category, payload, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, info_key) DO UPDATE SET
                category = excluded.category,
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (user_id, clean_key, clean_category, payload, now),
        )


def delete_private_info(user_id: str, info_key: str) -> bool:
    ensure_storage()
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM private_info WHERE user_id = ? AND info_key = ?",
            (user_id, _clean_key(info_key)),
        )
    return cursor.rowcount > 0


def save_application_draft(user_id: str, draft: dict) -> dict:
    ensure_storage()
    now = _now()
    draft_id = draft.get("id") or next_application_draft_id(user_id)
    draft["id"] = draft_id
    draft["created_at"] = draft.get("created_at") or now
    draft["updated_at"] = now
    payload = _encrypt_json(draft)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO application_drafts(user_id, draft_id, title, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, draft_id) DO UPDATE SET
                title = excluded.title,
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                draft_id,
                draft.get("title", "Application draft"),
                payload,
                draft["created_at"],
                now,
            ),
        )
    return draft


def load_application_drafts(user_id: str) -> list[dict]:
    ensure_storage()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT payload FROM application_drafts
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [_decrypt_json(row["payload"]) for row in rows]


def next_application_draft_id(user_id: str) -> str:
    ensure_storage()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT draft_id FROM application_drafts WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    max_num = 0
    for row in rows:
        raw = row["draft_id"]
        if isinstance(raw, str) and raw.startswith("a") and raw[1:].isdigit():
            max_num = max(max_num, int(raw[1:]))
    return f"a{max_num + 1:04d}"


def next_contact_id(user_id: str) -> str:
    ensure_storage()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT contact_id FROM contacts WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    max_num = 0
    for row in rows:
        raw = row["contact_id"]
        if isinstance(raw, str) and raw.startswith("c") and raw[1:].isdigit():
            max_num = max(max_num, int(raw[1:]))
    return f"c{max_num + 1:04d}"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _load_key() -> bytes:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(KEY_PATH):
        with open(KEY_PATH, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(KEY_PATH, "wb") as f:
        f.write(key)
    return key


def _fernet() -> Fernet:
    return Fernet(_load_key())


def _encrypt_json(data: Any) -> bytes:
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return _fernet().encrypt(raw)


def _decrypt_json(payload: bytes) -> Any:
    try:
        raw = _fernet().decrypt(payload)
    except InvalidToken as exc:
        raise RuntimeError(
            "Encrypted storage could not be unlocked. The local data key may "
            "be missing or mismatched."
        ) from exc
    return json.loads(raw.decode("utf-8"))


def _clean(value: str) -> str:
    return str(value or "").strip().lower()


def _clean_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower())
    key = re.sub(r"_+", "_", key).strip("_")
    return key or "general"


def _now() -> str:
    return datetime.datetime.now().isoformat()
