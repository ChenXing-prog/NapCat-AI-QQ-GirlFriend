"""User memory system.

Phase 1: Simple JSON file-based storage for single user.
Each user gets their own JSON file with:
- Basic profile (name, preferences)
- Recent conversation history (last N messages)
- Key events the bot should remember

Later phases can upgrade to PostgreSQL + vector DB.
"""

import json
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Optional


# Maximum number of recent conversation turns to keep in context
MAX_RECENT_MESSAGES = 20
# Maximum number of key events to remember
MAX_EVENTS = 50


@dataclass
class UserProfile:
    """A user's profile and memory."""

    user_id: str
    name: str = ""  # How the user wants to be called
    persona_id: str = "gentle"  # Selected persona
    preferences: dict[str, Any] = field(default_factory=dict)
    # Recent messages: list of {"role": "user"|"assistant", "content": str, "time": float}
    recent_messages: list[dict] = field(default_factory=list)
    # Key events: list of {
    #   "event": str, "type": str, "time": float,
    #   "extracted_at": float, "remind_in_hours": int, "reminded": bool
    # }
    events: list[dict] = field(default_factory=list)
    # Banned sticker filenames (per-user blacklist)
    banned_stickers: list[str] = field(default_factory=list)
    # Relationship stage: "new" | "familiar" | "close"
    relationship: str = "new"
    # Chat statistics
    first_chat: float = 0.0
    total_messages: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0

    def __post_init__(self):
        now = time.time()
        if not self.created_at:
            self.created_at = now
        if not self.first_chat:
            self.first_chat = now
        self.updated_at = now


class MemoryStore:
    """JSON file-based memory store for user profiles.

    Usage:
        store = MemoryStore(data_dir=Path("./data"))
        profile = store.get_user("123456")
        store.add_message("123456", "user", "你好呀～")
        messages = store.get_recent_messages("123456", count=10)
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.users_dir = data_dir / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # User profile
    # ------------------------------------------------------------------

    def get_user(self, user_id: str) -> UserProfile:
        """Get or create a user profile."""
        filepath = self._user_file(user_id)
        if filepath.exists():
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return UserProfile(**data)
        return UserProfile(user_id=user_id)

    def save_user(self, profile: UserProfile):
        """Save a user profile to disk."""
        profile.updated_at = time.time()
        filepath = self._user_file(profile.user_id)
        filepath.write_text(
            json.dumps(profile.__dict__, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _user_file(self, user_id: str) -> Path:
        """Get the file path for a user's profile."""
        # Sanitize user_id for filename
        safe_id = "".join(c for c in user_id if c.isalnum() or c in "-_")
        return self.users_dir / f"{safe_id}.json"

    # ------------------------------------------------------------------
    # Conversation memory
    # ------------------------------------------------------------------

    def add_message(self, user_id: str, role: str, content: str):
        """Record a message in the user's conversation history."""
        profile = self.get_user(user_id)
        profile.recent_messages.append({
            "role": role,
            "content": content,
            "time": time.time(),
        })
        profile.total_messages += 1

        # Trim old messages
        if len(profile.recent_messages) > MAX_RECENT_MESSAGES * 2:
            profile.recent_messages = profile.recent_messages[-MAX_RECENT_MESSAGES:]

        # Update relationship stage based on message count
        if profile.total_messages > 500:
            profile.relationship = "close"
        elif profile.total_messages > 100:
            profile.relationship = "familiar"

        self.save_user(profile)

    def get_recent_messages(self, user_id: str, count: int = MAX_RECENT_MESSAGES) -> list[dict]:
        """Get the most recent messages for a user."""
        profile = self.get_user(user_id)
        return profile.recent_messages[-count:]

    # ------------------------------------------------------------------
    # Event memory (enhanced for Phase 3)
    # ------------------------------------------------------------------

    def add_event(self, user_id: str, event: str, event_type: str = "personal",
                  remind_in_hours: int = 24, extracted_at: Optional[float] = None):
        """Record an important event with follow-up metadata.

        Args:
            user_id: The user's QQ number
            event: Description of the event
            event_type: exam|health|travel|work|personal|gaming|anime|social
            remind_in_hours: Hours until follow-up (0 = no follow-up)
            extracted_at: When the event was extracted (defaults to now)
        """
        profile = self.get_user(user_id)

        # Avoid duplicate events (same description within 24h)
        now = time.time()
        for existing in profile.events[-10:]:
            if existing.get("event") == event and (now - existing.get("time", 0)) < 86400:
                return  # Duplicate, skip

        profile.events.append({
            "event": event,
            "type": event_type,
            "time": now,
            "extracted_at": extracted_at or now,
            "remind_in_hours": remind_in_hours,
            "reminded": False,
        })

        # Trim old events
        if len(profile.events) > MAX_EVENTS:
            profile.events = profile.events[-MAX_EVENTS:]

        self.save_user(profile)

    def get_due_reminders(self, user_id: str) -> list[dict]:
        """Get events that are due for a follow-up reminder.

        Uses the Phase 3 enhanced event structure with remind_in_hours.
        """
        profile = self.get_user(user_id)
        now = time.time()
        due = []
        for e in profile.events:
            if e.get("reminded"):
                continue
            remind_hours = e.get("remind_in_hours", 0)
            if remind_hours <= 0:
                continue
            extracted_at = e.get("extracted_at", e.get("time", 0))
            hours_since = (now - extracted_at) / 3600
            if hours_since >= remind_hours:
                due.append(e)
                e["reminded"] = True  # Mark as reminded
        if due:
            self.save_user(profile)
        return due

    def mark_event_reminded(self, user_id: str, event_idx: int):
        """Mark a specific event as followed up."""
        profile = self.get_user(user_id)
        if 0 <= event_idx < len(profile.events):
            profile.events[event_idx]["reminded"] = True
            self.save_user(profile)

    # ------------------------------------------------------------------
    # Persona management
    # ------------------------------------------------------------------

    def set_persona(self, user_id: str, persona_id: str):
        """Change the user's selected persona."""
        profile = self.get_user(user_id)
        valid_personas = {"gentle", "tsundere", "genki", "oneesan", "otaku"}
        if persona_id in valid_personas:
            profile.persona_id = persona_id
            self.save_user(profile)

    # ------------------------------------------------------------------
    # Sticker blacklist
    # ------------------------------------------------------------------

    def ban_sticker(self, user_id: str, filename: str):
        """Add a sticker filename to the user's blacklist."""
        profile = self.get_user(user_id)
        if filename not in profile.banned_stickers:
            profile.banned_stickers.append(filename)
            self.save_user(profile)
            return True
        return False

    def unban_all_stickers(self, user_id: str):
        """Clear the user's sticker blacklist."""
        profile = self.get_user(user_id)
        profile.banned_stickers = []
        self.save_user(profile)

    def get_banned_stickers(self, user_id: str) -> set[str]:
        """Get the user's banned sticker filenames as a set."""
        profile = self.get_user(user_id)
        return set(profile.banned_stickers)

    # ------------------------------------------------------------------
    # Adaptive message gap tracking
    # ------------------------------------------------------------------

    def record_msg_gap(self, user_id: str, gap: float):
        """Record inter-message interval for adaptive buffer timing.

        Only keeps the last 20 gaps to adapt to changing typing patterns.
        """
        profile = self.get_user(user_id)
        gaps: list[float] = profile.preferences.get("msg_gaps", [])
        gaps.append(round(gap, 2))
        if len(gaps) > 20:
            gaps = gaps[-20:]
        profile.preferences["msg_gaps"] = gaps
        self.save_user(profile)

    def update_name(self, user_id: str, name: str):
        """Update the user's preferred name."""
        profile = self.get_user(user_id)
        profile.name = name
        self.save_user(profile)
