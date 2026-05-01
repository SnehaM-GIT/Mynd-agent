"""
daily_brief.py
──────────────────────────────────────────────────────────────────────
Generates a smart morning brief for the entrepreneur.

Includes:
  ✅ Today's calendar at a glance
  ✅ Unsent follow-ups (networking leads going cold)
  ✅ Top priority contacts to reach out to today
  ✅ Quick motivational context

Called from app.py on /brief command or when user says
"give me my daily brief" / "what's my morning plan"
──────────────────────────────────────────────────────────────────────
"""

import datetime
from networking_tool import (
    get_unsent_contacts,
    get_priority_contacts,
    get_networking_stats,
    format_contact_card,
)


def generate_daily_brief(calendar_events: list = None) -> str:
    """
    calendar_events: list of Google Calendar event dicts for today
    (already fetched from calendar_tool.get_events — pass raw items list)
    Pass None or [] if calendar fetch failed.
    """
    today     = datetime.date.today()
    now       = datetime.datetime.now()
    readable  = today.strftime("%A, %d %B %Y")
    hour      = now.hour
    greeting  = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

    lines = [f"# {greeting}, Suriya! 🚀", f"**{readable}**\n"]

    # ── Calendar section ───────────────────────────────────────────
    lines.append("## 📅 Today's Schedule")

    if calendar_events:
        for event in calendar_events:
            title = event.get("summary", "Untitled")
            start = event["start"].get("dateTime", "")
            if start:
                t = datetime.datetime.fromisoformat(start)
                time_str = t.strftime("%I:%M %p")
            else:
                time_str = "All day"
            lines.append(f"⏰ {time_str} — **{title}**")
    else:
        lines.append("✨ No events scheduled — a free day to build!")

    lines.append("")

    # ── Networking section ─────────────────────────────────────────
    unsent = get_unsent_contacts(days_threshold=0)   # all unsent, any age
    stale  = get_unsent_contacts(days_threshold=3)   # unsent for 3+ days
    top    = get_priority_contacts(top_n=3)
    stats  = get_networking_stats()

    lines.append("## 🤝 Networking Priorities")

    if stats["total"] == 0:
        lines.append("No contacts yet. After your next event, tell me who you met!")
    else:
        lines.append(f"👥 **{stats['total']}** contacts · "
                     f"✅ **{stats['sent']}** followed up · "
                     f"⏳ **{stats['unsent']}** pending")

        if stale:
            lines.append(
                f"\n⚠️ **{len(stale)} contact(s) going cold** "
                f"(no follow-up in 3+ days):"
            )
            for c in stale[:3]:
                lines.append(
                    f"  • **{c['name']}** — met at {c.get('event','?')} "
                    f"· {c.get('role','')}"
                )

        if top and stats["unsent"] > 0:
            lines.append("\n🎯 **Top contacts to reach today:**")
            for c in top:
                if not c.get("message_sent"):
                    lines.append(
                        f"  • **{c['name']}** ({c.get('company','')}) "
                        f"— Score {c.get('score',0)}/100"
                    )

    lines.append("")

    # ── Quick actions ──────────────────────────────────────────────
    lines.append("## ⚡ Quick Actions")
    lines.append("Say **send followup to [name]** to generate a message")
    lines.append("Say **show contacts from [event]** to see event contacts")
    lines.append("Say **block [time] for [task]** to add a calendar event")
    lines.append("Say **/stats** to see your full networking stats")

    return "\n".join(lines)