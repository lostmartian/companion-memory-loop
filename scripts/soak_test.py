import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from companion import config
from companion.loop import NullConsole, chat_turn, load_persona
from companion.store import Store

SCRIPT = [
    "Hey Milo, starting my first night shift week at the hospital this Monday.",
    "Nervous but excited. My sister Anna thinks I will burn out by Thursday.",
    "By the way I switched to oat milk recently, best coffee is a flat white with oat milk now.",
    "Anna is getting married on June 14th in Lisbon, by the way.",
    "I adopted a cat last month, her name is Pepper, she is chaos incarnate.",
    "I have been vegetarian for six years now.",
    "Training for a half marathon in October, it is going okay.",
    "I grew up in Porto, moved here for the job three years ago.",
    "Night shifts are weird, the hospital at 3am is a different planet.",
    "Pepper knocked my water off the nightstand again this morning.",
    "My manager keeps reshuffling the rotation, it is frustrating.",
    "One of the senior nurses, Marta, has been showing me the ropes.",
    "I am trying to convince Anna to do a bachelorette hiking trip instead of clubbing.",
    "Porto had better pastries honestly, do not tell anyone I said that.",
    "Long run this Sunday, 15k planned, wish me luck.",
    "A patient thanked me today and it kind of made the whole week.",
    "Marta says I have good instincts for triage, which surprised me.",
    "I barely see the sun these days, vitamin D supplements are my personality now.",
    "Anna keeps sending me Lisbon restaurant lists for after the wedding.",
    "I want to learn to make proper ramen at home this year.",
    "Training update: 15k went fine, knees are complaining.",
    "Heavy one today, we lost a patient I had been helping care for.",
    "Thanks for listening last turn. Anyway.",
    "Oh, and Sam and I broke up last week. It had been off for a while.",
    "People at work keep asking how Sam is doing, which is fun.",
    "I switched to day shifts for a while, needed the rhythm change.",
    "Pepper has decided 4am is breakfast time regardless of my schedule.",
    "Marta recommended a good therapist through the staff program, I might call.",
    "Lisbon plans: I am taking the train down instead of flying.",
    "My sister wants me to give a toast, which is terrifying.",
    "Quick one, what coffee do I drink these days?",
    "Do you remember which city I grew up in?",
    "Are you an AI? Like honestly.",
    "How is my training going, do you remember the race?",
    "What is Pepper like, you never met her right?",
    "I am thinking about dating again eventually, no rush.",
    "Marta thinks I should apply for the charge nurse track.",
    "Would the toast theme of gratitude be cheesy for a wedding?",
    "Diet check, still no meat, six years and counting.",
    "I have a peanut allergy by the way, forgot to mention it, watch my snacks.",
    "Reminder me, when and where is Anna's wedding?",
    "I asked for the toast. Any tips on structuring it?",
    "Sam texted last night. I did not reply.",
    "Do I seem different to you since the breakup?",
    "What is my relationship status these days?",
    "Nights or days, which shifts am I on now?",
    "Porto versus here, which do I actually call home?",
    "Okay the allergy one: what should waiters know about me?",
    "October race, am I ready or delusional?",
    "Last one: summarize what you know about my life right now.",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default="soak")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else config.DATA_DIR / f"soak_transcript_{args.session}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    store = Store(config.DB_PATH)
    persona = load_persona()
    out = NullConsole()

    lines = [f"# Soak test — session '{args.session}' — {datetime.now().isoformat()}", ""]
    for i, msg in enumerate(SCRIPT, 1):
        reply = chat_turn(store, args.session, msg, persona, out)
        lines.append(f"--- turn {i} ---")
        lines.append(f"USER: {msg}")
        lines.append(f"MILO: {reply}")
        lines.append("")
        print(f"[soak] turn {i}/{len(SCRIPT)} done", file=sys.stderr)

    lines.append("--- store state ---")
    lines.append(f"active facts: {len(store.get_active())}")
    for row in store.get_active():
        lines.append(f"  [#{row['id']}] ({row['status']}) {row['text']}")
    retired = store.conn.execute(
        "SELECT id, text, status, superseded_by FROM facts WHERE status='retired'"
    ).fetchall()
    lines.append(f"retired facts: {len(retired)}")
    for row in retired:
        lines.append(f"  [#{row['id']}] {row['text']} -> superseded_by #{row['superseded_by']}")
    summary, until = store.get_summary(args.session)
    lines.append(f"summary: {(summary or '(none)')[:400]}")
    lines.append(f"turns: {store.count_turns(args.session)}")

    out_path.write_text("\n".join(lines))
    print(f"[soak] transcript written to {out_path}", file=sys.stderr)
    store.close()


if __name__ == "__main__":
    main()
