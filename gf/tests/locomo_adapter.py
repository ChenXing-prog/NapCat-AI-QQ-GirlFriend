"""LoCoMo adapter — uses our MemoryStore + moonshot-v1-8k for memory testing."""

import json, time, sys, os
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Override paths for local testing
os.environ["DATA_DIR"] = str(Path(__file__).parent / "output" / "mem_data")
os.environ["STICKERS_DIR"] = str(Path(__file__).parent.parent.parent / "stickers")

from gf.config import load_config
from gf.memory.store import MemoryStore
from gf.ai.llm import LLMClient

load_config()


class OurMemoryTester:
    """Tests our memory system using LoCoMo benchmark sessions."""

    def __init__(self, output_dir: Path):
        self.store = MemoryStore(output_dir / "mem_data")
        self.llm = LLMClient(load_config().llm)
        self.output_dir = output_dir

    def process_session(self, character_name: str, session: list[dict]) -> int:
        """Process a conversation session through our memory pipeline.

        Each session is a list of {speaker, text, session} dicts.
        Returns number of messages processed.
        """
        user_id = f"locomo_{character_name}"
        # Flatten session into messages
        count = 0
        batch = []
        for turn in session:
            role = "user" if "user" in turn.get("speaker", "").lower() else "assistant"
            text = turn.get("text", "")
            if not text:
                continue
            self.store.add_message(user_id, role, text)
            count += 1
            batch.append({"role": role, "content": text})

        # Run memory extraction (manually trigger at the end of each session)
        # We'll batch process after all sessions
        return count

    def finalize_memory(self, character_name: str):
        """After all sessions, run extraction pipeline in batches."""
        user_id = f"locomo_{character_name}"
        recent = self.store.get_recent_messages(user_id, 50)

        import asyncio
        from gf.ai.memory import _lite_chat, _parse_json

        async def extract():
            # Batch: process in chunks of 30 messages
            batch_size = 30
            total_facts = 0
            for i in range(0, len(recent), batch_size):
                batch = recent[i:i + batch_size]
                conv = "\n".join(f"U: {m['content'][:150]}" for m in batch)

                # Facts
                raw = await _lite_chat(
                    "提取关键事实。只输出JSON：{\"facts\":[{\"subject\":\"user\",\"category\":\"...\",\"content\":\"...\",\"importance\":1-10}]}",
                    conv[:3000], 500,
                )
                facts = _parse_json(raw).get("facts", [])
                if facts:
                    self.store.add_facts(user_id, facts)
                    total_facts += len(facts)

                # Summary
                raw2 = await _lite_chat(
                    "压缩对话为摘要。只输出JSON：{\"summary\":\"...\",\"key_topics\":[\"...\"],\"high_importance\":false,\"archive\":[{\"content\":\"原话\",\"context\":\"背景\",\"emotion\":\"...\",\"importance\":8}]}",
                    conv[:4000], 800,
                )
                data = _parse_json(raw2)
                if data.get("summary"):
                    self.store.add_summary(user_id, f"batch{i//batch_size+1}", data["summary"], data.get("key_topics", []), len(batch), data.get("high_importance", False))
                for a in data.get("archive", []):
                    self.store.add_archive(user_id, a.get("content", ""), a.get("context", ""), a.get("emotion", "neutral"), a.get("importance", 8))

            print(f"  Memory extracted: {total_facts} facts, {len(recent)//batch_size + 1} summary batches")

        asyncio.run(extract())

    def answer_question(self, character_name: str, question: str) -> str:
        """Answer using our memory retrieval + LLM."""
        user_id = f"locomo_{character_name}"
        facts = self.store.get_context_facts(user_id, limit=10)
        summaries = self.store.get_context_summaries(user_id, limit=2)
        archive = self.store.search_archive(user_id, query=question, limit=1)

        context = ""
        if facts:
            context += "已知信息：\n" + "\n".join(f"- {f['content']}" for f in facts) + "\n"
        if summaries:
            context += "对话摘要：\n" + "\n".join(s["summary"][:150] for s in summaries) + "\n"
        if archive:
            a = archive[0]
            context += f"重要回忆：{a['content']}\n"

        prompt = f"""根据以下信息回答问题。只输出答案，不要解释。

{context}
问题：{question}"""

        import asyncio
        async def ask():
            reply, _ = await self.llm.chat([
                LLMClient.system_message("你是一个助手。根据给定信息回答问题。只输出答案，不要解释。如果信息不足，回答'不知道'。"),
                LLMClient.user_message(prompt),
            ])
            return reply.strip()
        return asyncio.run(ask())
