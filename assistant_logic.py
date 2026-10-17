"""Conversation and document rules shared by the HTTP handler and checks."""
import re

TASKS = {
    "chat": "",
    "troubleshoot": (
        "Help troubleshoot the reported equipment issue. Structure the answer as "
        "reported symptoms, documented safety precautions, documented checks, and "
        "escalation criteria. Ask for missing equipment IDs or error codes. "
        "Never invent procedures, limits, or diagnostic results."
    ),
    "checklist": (
        "Create a service checklist with [ ] items, grouped into preparation, "
        "documented service steps, and completion checks where supported. "
        "Cite every documented instruction. Omit unsupported steps and explicitly "
        "identify missing instructions. Never invent safety procedures or measurements."
    ),
    "ticket": (
        "Draft an escalation ticket with equipment/model, serial number, firmware, "
        "symptoms and error codes, actions already taken, impact, and next owner. "
        "Use only facts explicitly supplied by the user for incident details. "
        "Mark missing fields as [To be provided]. Cite documented escalation rules. "
        "Do not invent completed actions or send the ticket."
    ),
}


def messages_for(history, system, task="chat"):
    """Keep the system prompt and a bounded sequence starting with a user."""
    turns = [dict(m) for m in history if m["role"] != "system"][-31:]
    # Leave room for retrieved passages and the answer on smaller local models.
    while len(turns) > 1 and sum(len(m["content"]) for m in turns) > 12000:
        turns.pop(0)
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    instructions = TASKS.get(task, "")
    return [{"role": "system", "content": system + "\n\n" + instructions}] + turns


def retrieval_query(message, previous):
    """Resolve short referential follow-ups from the last user question."""
    if previous and re.search(r"\b(it|its|that|those|them|this|same)\b", message, re.I):
        return previous[-700:] + "\n" + message
    return message


STOP_WORDS = set("tell about what when where does have with that this from will "
                 "would could should please give show explain describe more some "
                 "there their much many also into over only very which while these "
                 "those than then were just like want need know create draft service "
                 "checklist ticket help make document documents using according "
                 "and the for are how can you our its has".split())


def relevant_sources(query, sources):
    tokens = {t for t in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", query.lower())
              if len(t) >= 2 and t not in STOP_WORDS}
    return [c for c in sources if c["score"] >= 0.45 and tokens and
            any(t in (c["text"] + " " + c["source"]).lower() for t in tokens)][:4]
