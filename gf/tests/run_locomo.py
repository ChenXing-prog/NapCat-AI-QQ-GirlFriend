#!/usr/bin/env python3
"""Run LoCoMo memory test against our bot's memory system."""

import json, time, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from gf.tests.locomo_adapter import OurMemoryTester

DATA_FILE = Path(__file__).parent / "test_data" / "locomo10.json"
OUTPUT_DIR = Path(__file__).parent / "output"
MEM_DIR = Path(__file__).parent / "memory"


def main(sample_limit: int = 1):
    # Load data
    with open(DATA_FILE) as f:
        data = json.load(f)
    samples = data if isinstance(data, list) else data.get("samples", [data])
    print(f"Loaded {len(samples)} samples, using first {sample_limit}")

    tester = OurMemoryTester(OUTPUT_DIR)
    results = []

    for idx in range(min(sample_limit, len(samples))):
        sample = samples[idx]
        conversation = sample["conversation"]
        speaker_a = conversation.get("speaker_a", "User")
        speaker_b = conversation.get("speaker_b", "Assistant")
        character = f"{speaker_b}_{idx}"
        questions = sample.get("qa", [])

        # Extract sessions
        sessions = []
        for key in sorted(conversation.keys()):
            if key.startswith("session_") and not key.endswith("_date_time"):
                if isinstance(conversation[key], list):
                    sessions.append(conversation[key])

        print(f"\n[{idx}] {speaker_a} & {speaker_b}: {len(sessions)} sessions, {len(questions)} questions")

        # Process sessions
        total_msgs = 0
        for sess in sessions:
            total_msgs += tester.process_session(character, sess)
        print(f"  Processed {total_msgs} messages")
        tester.finalize_memory(character)
        print(f"  Total archive entries: ", end="")
        archive_path = tester.store._archive_path(f"locomo_{character}")
        if archive_path.exists():
            lines = open(archive_path).readlines()
            print(f"{len(lines)} from LoCoMo test")
        else:
            print("0")

        # Answer questions
        correct = 0
        total = 0
        for q in questions:
            total += 1
            q_text = q.get("question", "")
            expected = q.get("answer", "")
            got = tester.answer_question(character, q_text)
            # Simple string match evaluation
            exp_str = str(expected).strip().lower()
            got_str = str(got).strip().lower()
            is_correct = exp_str in got_str or got_str in exp_str
            if is_correct:
                correct += 1
            if total <= 3:
                print(f"  Q: {q_text[:60]}")
                g = str(got)[:80]; e = str(expected)[:60]
                print(f"  A: {g} | Expected: {e} | {'OK' if is_correct else 'WRONG'}")
        acc = correct / total * 100 if total else 0
        print(f"  Accuracy: {correct}/{total} = {acc:.1f}%")
        results.append({"character": character, "accuracy": acc, "correct": correct, "total": total})

    # Summary
    if results:
        avg = sum(r["accuracy"] for r in results) / len(results)
        print(f"\n=== Summary ===")
        print(f"Overall accuracy: {avg:.1f}% ({sum(r['correct'] for r in results)}/{sum(r['total'] for r in results)})")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-n", "--samples", type=int, default=1, help="Number of samples to test")
    args = p.parse_args()
    main(args.samples)
