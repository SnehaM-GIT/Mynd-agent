import datetime
import json
import os
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


def _now() -> str:
    return datetime.datetime.now().isoformat()
