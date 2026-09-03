import sys

from google.genai import types
from rich.console import Console

from companion import compaction, config, extract, llm, retrieve
from companion.contradictions import process_fact
from companion.persona import grounding_block, is_pressure_turn, load_persona
from companion.store import Store

console = Console()


class NullConsole:
    def print(self, *args, **kwargs):
        pass

    def input(self, *args, **kwargs):
        raise EOFError


def build_history(store: Store, session_id: str) -> list[types.Content]:
    turns = store.get_turns(session_id, limit=config.RECENT_TURNS + 1)
    if turns and turns[-1]["role"] == "user":
        turns = turns[:-1]
    history = []
    for t in turns:
        role = "user" if t["role"] == "user" else "model"
        history.append(types.Content(role=role, parts=[types.Part(text=t["content"])]))
    return history


def chat_turn(
    store: Store,
    session_id: str,
    user_input: str,
    persona: str,
    out=console,
) -> str:
    store.add_turn(session_id, "user", user_input)

    summary = compaction.compact_if_needed(store, session_id)
    recalled = retrieve.retrieve(store, user_input)
    system_parts = [persona]
    if summary:
        system_parts.append(f"Conversation so far:\n{summary}")
    if is_pressure_turn(user_input):
        system_parts.append(grounding_block())
        out.print("  [dim]re-grounded persona[/dim]")
    if recalled:
        lines = [f"- {row['text']}" for row, _ in recalled]
        system_parts.append(
            "Things you remember about the user (use naturally, never recite as a list):\n"
            + "\n".join(lines)
        )
    system = "\n\n".join(system_parts)
    for row, _ in recalled:
        out.print(f"  [dim]recalled: {row['text']}[/dim]")

    history = build_history(store, session_id)

    reply_parts = []
    try:
        for chunk in llm.generate_stream(user_input, system=system, history=history):
            out.print(chunk, end="")
            reply_parts.append(chunk)
        out.print()
    except Exception as e:
        out.print(f"\n[red]stream error: {e}[/red]")
        reply_parts = [llm.generate(user_input, system=system, history=history)]
        out.print(reply_parts[0])

    reply = "".join(reply_parts).strip()
    if reply:
        store.add_turn(session_id, "assistant", reply)

    recent = [t["content"] for t in store.get_turns(session_id, limit=4)]
    facts = extract.extract_facts(user_input, recent_context="\n".join(recent[:-1]))
    for f in facts:
        action = process_fact(store, f, source_turn=store.count_turns(session_id))
        out.print(f"  [dim]memory ({action}): {f.text}[/dim]")

    return reply


def run(session_id: str = "main") -> None:
    store = Store(config.DB_PATH)
    persona = load_persona()
    prior = store.count_turns(session_id)
    if prior:
        console.print(f"[dim]Resuming session '{session_id}' ({prior} prior turns)[/dim]")
    console.print(f"[bold cyan]Milo[/bold cyan] [dim]— session '{session_id}'. Type /exit to quit.[/dim]")

    while True:
        try:
            user_input = console.input("[bold green]you ›[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input == "/exit":
            break
        if user_input == "/facts":
            for row in store.get_active(subject="user"):
                console.print(f"  [dim]#{row['id']}[/dim] {row['text']}")
            continue

        chat_turn(store, session_id, user_input, persona, console)

    store.close()
    console.print("[dim]bye — memories saved.[/dim]")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "main")
