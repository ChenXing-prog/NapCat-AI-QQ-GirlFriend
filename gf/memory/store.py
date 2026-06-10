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
    # Long-term memory
    core_facts: list[dict] = field(default_factory=list)  # [{subject, category, content, importance, ...}]
    summaries: list[dict] = field(default_factory=list)    # [{date_range, summary, key_topics, message_count, high_importance, ...}]
    emotion_log: list[dict] = field(default_factory=list)  # [{date, dominant, intensity, note, msg_count}]
    shared_moments: list[dict] = field(default_factory=list)  # [{type, content, created_at, importance, recalled_count}]
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
        valid_personas = {"gentle", "tsundere", "genki", "oneesan", "otaku", "coder"}
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
    # Emotion trajectory
    # ------------------------------------------------------------------

    def log_emotion(self, user_id: str, dominant: str, intensity: float, note: str, msg_count: int):
        """Record daily emotional summary."""
        from datetime import date
        today = date.today().isoformat()
        profile = self.get_user(user_id)
        # Update today's entry if exists, else append
        for e in profile.emotion_log:
            if e.get("date") == today:
                e["dominant"] = dominant
                e["intensity"] = intensity
                e["note"] = note
                e["msg_count"] = msg_count
                self.save_user(profile)
                return
        profile.emotion_log.append({
            "date": today, "dominant": dominant,
            "intensity": intensity, "note": note, "msg_count": msg_count,
        })
        if len(profile.emotion_log) > 30:
            profile.emotion_log = profile.emotion_log[-30:]
        self.save_user(profile)

    def get_emotion_trajectory(self, user_id: str, days: int = 7) -> list[dict]:
        """Get recent emotion history for context injection."""
        profile = self.get_user(user_id)
        return profile.emotion_log[-days:]

    # ------------------------------------------------------------------
    # Shared moments
    # ------------------------------------------------------------------

    def add_moment(self, user_id: str, moment_type: str, content: str, importance: int = 5):
        """Record a shared moment (milestone, late night, confide, etc)."""
        profile = self.get_user(user_id)
        # Avoid duplicates within 3 days
        import time
        now = time.time()
        for m in profile.shared_moments[-10:]:
            if m["content"] == content and (now - m["created_at"]) < 259200:
                return
        profile.shared_moments.append({
            "type": moment_type, "content": content,
            "created_at": now, "importance": importance, "recalled_count": 0,
        })
        if len(profile.shared_moments) > 50:
            profile.shared_moments = profile.shared_moments[-50:]
        self.save_user(profile)

    def get_random_moment(self, user_id: str) -> dict | None:
        """Get a mostly-unrecalled moment for natural reference."""
        import random
        profile = self.get_user(user_id)
        if not profile.shared_moments:
            return None
        # Prefer low recall count, higher importance
        candidates = [m for m in profile.shared_moments if m.get("recalled_count", 0) < 2]
        if not candidates:
            return None
        weights = [m.get("importance", 5) for m in candidates]
        chosen = random.choices(candidates, weights=weights, k=1)[0]
        chosen["recalled_count"] = chosen.get("recalled_count", 0) + 1
        self.save_user(profile)
        return chosen

    def get_milestone_moments(self, user_id: str) -> list[dict]:
        """Get milestone-type moments (for relationship summary)."""
        profile = self.get_user(user_id)
        return [m for m in profile.shared_moments if m.get("type") == "milestone"]

    # ------------------------------------------------------------------
    # Core archive — permanent memory vault (JSONL, per-user, attenuation)
    # ------------------------------------------------------------------

    _EMO_GROUPS = {
        "vulnerable": "soft", "sad": "soft", "anxious": "soft", "tired": "soft",
        "intimate": "warm", "warm": "warm", "grateful": "warm", "happy": "warm",
    }

    def _archive_path(self, user_id: str) -> Path:
        safe = "".join(c for c in user_id if c.isalnum() or c in "-_")
        return self.users_dir / f"{safe}_archive.jsonl"

    def add_archive(self, user_id: str, content: str, context: str = "",
                    emotion: str = "neutral", importance: int = 8):
        """Append to per-user archive.jsonl. No capacity limit."""
        entry = {
            "content": content,
            "context": context,
            "emotion": emotion,
            "importance": importance,
            "recalled_count": 0,
            "created_at": time.time(),
        }
        import json
        path = self._archive_path(user_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _attenuate(self, recalled_count: int, importance: int, created_at: float) -> float:
        """Calculate attenuation. Higher = more retrievable.
        - importance≥9: decays very slowly (years)
        - importance≥7: decays over months
        - importance<7: decays over weeks
        - recalled_count resets the curve
        """
        months = (time.time() - created_at) / 2592000
        base = importance / 10.0
        decay = 1.0 / (1.0 + months * (1.0 - base))
        recall_bonus = 1.0 + min(recalled_count, 10) * 0.15  # up to +150%
        return base * decay * recall_bonus

    def search_archive(self, user_id: str, query: str = "", emotion_group: str = "",
                       limit: int = 1) -> list[dict]:
        """Search archive with attenuation filter. Only scans last 500 entries."""
        import json, random
        path = self._archive_path(user_id)
        if not path.exists():
            return []
        candidates = []
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-500:]
        for line in lines:
            a = json.loads(line)
            imp = a.get("importance", 5)
            # Skip low-importance entries for keyword search
            if query and imp < 7:
                continue
            match = True
            if query:
                match = query in a.get("content", "") or query in a.get("context", "")
            if emotion_group:
                emo = a.get("emotion", "")
                if self._EMO_GROUPS.get(emo) != emotion_group:
                    match = False
            if match:
                score = self._attenuate(a.get("recalled_count", 0), imp, a.get("created_at", time.time()))
                if score > 0.3:  # Below threshold = functionally forgotten
                    candidates.append((score, a))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in candidates[:limit]] if candidates else []

    def get_archive_by_emotion(self, user_id: str, emotion: str, limit: int = 1) -> list[dict]:
        """Get archive entries matching an emotion group."""
        group = self._EMO_GROUPS.get(emotion)
        return self.search_archive(user_id, emotion_group=group, limit=limit) if group else []

    def bump_archive_recall(self, user_id: str, content: str):
        """Increment recalled_count for an archive entry (resets decay curve)."""
        import json
        path = self._archive_path(user_id)
        if not path.exists():
            return
        lines = []
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(path, "w", encoding="utf-8") as f:
            for line in lines:
                a = json.loads(line)
                if a.get("content") == content:
                    a["recalled_count"] = a.get("recalled_count", 0) + 1
                f.write(json.dumps(a, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------
    # Adaptive message gap tracking
    # ------------------------------------------------------------------

    def record_msg_gap(self, user_id: str, gap: float):
        """Record inter-message interval for adaptive buffer timing.

        Keeps up to 50 historical gaps for long-term average calculation.
        Session gaps (stored separately) are used for current-conversation weighting.
        """
        profile = self.get_user(user_id)
        gaps: list[float] = profile.preferences.get("msg_gaps", [])
        gaps.append(round(gap, 2))
        if len(gaps) > 50:
            gaps = gaps[-50:]
        profile.preferences["msg_gaps"] = gaps
        self.save_user(profile)

    # ------------------------------------------------------------------
    # Long-term memory: Core Facts
    # ------------------------------------------------------------------

    def add_facts(self, user_id: str, facts: list[dict]):
        """Merge new facts into core_facts. Facts are [{subject, category, content, importance}].

        subject: "user" (about the user) or "me" (about the AI girlfriend herself).
        """
        profile = self.get_user(user_id)
        now = time.time()
        for f in facts:
            existing = [e for e in profile.core_facts if e["content"] == f["content"]]
            if existing:
                existing[0]["last_accessed"] = now
                existing[0]["access_count"] = existing[0].get("access_count", 0) + 1
                existing[0]["importance"] = max(existing[0].get("importance", 1), f.get("importance", 5))
                continue
            profile.core_facts.append({
                "subject": f.get("subject", "user"),
                "category": f.get("category", "personal_info"),
                "content": f["content"],
                "importance": f.get("importance", 5),
                "created_at": now,
                "last_accessed": now,
                "access_count": 0,
            })

        # Trim: keep top 50 by importance
        if len(profile.core_facts) > 50:
            profile.core_facts.sort(key=lambda x: x.get("importance", 0), reverse=True)
            profile.core_facts = profile.core_facts[:50]

        # Consolidate similar facts if > 40
        if len(profile.core_facts) > 40:
            profile.core_facts = self._consolidate_facts(profile.core_facts)

        self.save_user(profile)

    def _consolidate_facts(self, facts: list[dict]) -> list[dict]:
        """Simple dedup by category + first 4 chars of content."""
        seen = {}
        for f in facts:
            key = (f.get("category", ""), f["content"][:4])
            if key in seen:
                # Merge: take higher importance, longer content
                existing = seen[key]
                if f["importance"] > existing["importance"]:
                    existing["importance"] = f["importance"]
                if len(f["content"]) > len(existing["content"]):
                    existing["content"] = f["content"]
            else:
                seen[key] = f
        return sorted(seen.values(), key=lambda x: x.get("importance", 0), reverse=True)

    def get_context_facts(self, user_id: str, limit: int = 20) -> list[dict]:
        """Get top facts for LLM context. Returns user facts + 1-2 'me' facts."""
        profile = self.get_user(user_id)
        now = time.time()
        scored = []
        for f in profile.core_facts:
            age_days = (now - f.get("created_at", now)) / 86400
            recency = 1.0 / (1.0 + age_days)
            importance = f.get("importance", 5) / 10.0
            accesses = min(f.get("access_count", 0), 10) / 10.0
            score = importance * 0.5 + recency * 0.3 + accesses * 0.2
            scored.append((score, f))
        scored.sort(key=lambda x: x[0], reverse=True)
        # Split user vs me
        user_facts = [f for _, f in scored if f.get("subject", "user") == "user"][:limit - 2]
        me_facts = [f for _, f in scored if f.get("subject") == "me"][:2]
        # Interleave: user fact, maybe me fact, user fact, maybe me fact...
        result = []
        for i, uf in enumerate(user_facts):
            result.append(uf)
            if i % 6 == 5 and me_facts:
                result.append(me_facts.pop(0))
        return result

    # ------------------------------------------------------------------
    # Long-term memory: Summaries
    # ------------------------------------------------------------------

    def add_summary(self, user_id: str, date_range: str, summary: str,
                    key_topics: list[str], message_count: int, high_importance: bool = False):
        """Add a conversation batch summary."""
        profile = self.get_user(user_id)
        profile.summaries.append({
            "date_range": date_range,
            "summary": summary,
            "key_topics": key_topics,
            "message_count": message_count,
            "high_importance": high_importance,
            "created_at": time.time(),
        })
        # Trim old, but preserve high_importance ones
        if len(profile.summaries) > 10:
            old = profile.summaries[:-3]
            if len(old) >= 2:
                important = [s for s in old if s.get("high_importance")]
                regular = [s for s in old if not s.get("high_importance")]
                if len(regular) >= 2:
                    compressed = self._compress_summaries(regular)
                    profile.summaries = important + [compressed] + profile.summaries[-3:]
                    if len(profile.summaries) > 15:
                        profile.summaries = profile.summaries[-15:]
                else:
                    profile.summaries = profile.summaries[-12:]
            else:
                profile.summaries = profile.summaries[-10:]
        self.save_user(profile)

    def _compress_summaries(self, old: list[dict]) -> dict:
        """Merge multiple summaries into one super-summary."""
        topics = set()
        total_msgs = 0
        parts = []
        for s in old:
            topics.update(s.get("key_topics", []))
            total_msgs += s.get("message_count", 0)
            parts.append(s["summary"])
        return {
            "date_range": f"{old[0]['date_range'].split('-')[0]}-{old[-1]['date_range'].split('-')[-1]}",
            "summary": "；".join(parts),
            "key_topics": list(topics)[:10],
            "message_count": total_msgs,
            "created_at": time.time(),
        }

    def get_context_summaries(self, user_id: str, limit: int = 3) -> list[dict]:
        """Get recent summaries for LLM context."""
        profile = self.get_user(user_id)
        return profile.summaries[-limit:]

    # ------------------------------------------------------------------

    def update_name(self, user_id: str, name: str):
        """Update the user's preferred name."""
        profile = self.get_user(user_id)
        profile.name = name
        self.save_user(profile)
