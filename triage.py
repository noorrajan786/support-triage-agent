"""Support Triage Agent with a feedback loop.

  python triage.py draft  --run v1 --no-feedback   # baseline drafts
  python triage.py review --run v1                 # approve / edit / reject each draft
  python triage.py draft  --run v2                 # drafts that learn from past human edits
  python triage.py review --run v2
  python triage.py report                          # compare acceptance rates by run
"""
import argparse, glob, json, time
from pathlib import Path
import anthropic
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

MODEL = "claude-sonnet-5-5"
CATEGORIES = ["assignment", "access", "configuration", "performance", "other"]
DRAFTS, REVIEWS = Path("drafts.jsonl"), Path("reviews.jsonl")
client = anthropic.Anthropic()


def ask(prompt, max_tokens=800):
    r = client.messages.create(model=MODEL, max_tokens=max_tokens,
                               messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in r.content if b.type == "text").strip()


def read_jsonl(path):
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()] if path.exists() else []


def append_jsonl(path, row):
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


class KnowledgeBase:
    def __init__(self, folder="kb"):
        self.docs = []
        for f in sorted(glob.glob(f"{folder}/*.md")):
            text = Path(f).read_text()
            self.docs.append({"title": text.splitlines()[0].lstrip("# ").strip(), "text": text})
        self.vec = TfidfVectorizer(stop_words="english")
        self.matrix = self.vec.fit_transform([d["text"] for d in self.docs])

    def search(self, query, k=2):
        scores = cosine_similarity(self.vec.transform([query]), self.matrix)[0]
        return [self.docs[i] for i in scores.argsort()[::-1][:k]]


def classify(ticket):
    out = ask(f"Classify this support ticket into one of {CATEGORIES}. Reply with the category word only.\n\n"
              f"{ticket['subject']}\n{ticket['body']}")
    out = out.lower().strip(" .")
    return out if out in CATEGORIES else "other"


def past_corrections(category, n=3):
    """The feedback loop: reuse recent human edits for this category as examples."""
    drafts = {(d["run"], d["id"]): d for d in read_jsonl(DRAFTS)}
    rows = [r for r in read_jsonl(REVIEWS) if r["action"] == "edited" and r["category"] == category]
    return [(drafts[(r["run"], r["id"])]["ticket_text"], r["final"]) for r in rows[-n:] if (r["run"], r["id"]) in drafts]


def draft_reply(ticket, category, kb, use_feedback):
    docs = kb.search(ticket["subject"] + " " + ticket["body"])
    context = "\n\n".join(f"[{d['title']}]\n{d['text']}" for d in docs)
    prompt = ("Draft a reply to this support ticket using ONLY the knowledge base articles below. "
              "Cite the article title in brackets after each step that uses it. "
              "If the articles do not answer the ticket, say so and recommend escalation.\n\n"
              f"Ticket: {ticket['subject']}\n{ticket['body']}\n\nKnowledge base:\n{context}")
    examples = past_corrections(category) if use_feedback else []
    if examples:
        prompt += "\n\nA human agent corrected earlier drafts like this. Match their style and fixes:\n"
        for t, final in examples:
            prompt += f"\nTicket: {t}\nCorrected reply: {final}\n"
    return ask(prompt, 1000), [d["title"] for d in docs], len(examples)


def cmd_draft(a):
    kb = KnowledgeBase()
    for t in json.loads(Path(a.tickets).read_text()):
        cat = classify(t)
        text, sources, n_ex = draft_reply(t, cat, kb, not a.no_feedback)
        append_jsonl(DRAFTS, {"run": a.run, "id": t["id"], "category": cat, "sources": sources,
                              "ticket_text": f"{t['subject']}: {t['body']}", "draft": text,
                              "examples_used": n_ex})
        print(f"{a.run} #{t['id']} [{cat}] drafted (examples used: {n_ex})")


def read_multiline():
    lines = []
    while (l := input()) != "":
        lines.append(l)
    return "\n".join(lines)


def cmd_review(a):
    done = {(r["run"], r["id"]) for r in read_jsonl(REVIEWS)}
    todo = [d for d in read_jsonl(DRAFTS) if d["run"] == a.run and (d["run"], d["id"]) not in done]
    for d in todo:
        print(f"\n=== #{d['id']} [{d['category']}] sources: {d['sources']}\nTICKET: {d['ticket_text']}\n\nDRAFT:\n{d['draft']}")
        choice = ""
        while choice not in ("a", "e", "r"):
            choice = input("\n(a)pprove  (e)dit  (r)eject > ").strip().lower()
        final = d["draft"]
        if choice == "e":
            print("Type the corrected reply, then a blank line:")
            final = read_multiline()
        action = {"a": "approved", "e": "edited", "r": "rejected"}[choice]
        append_jsonl(REVIEWS, {"run": a.run, "id": d["id"], "category": d["category"],
                               "action": action, "final": final, "ts": time.time()})


def cmd_report(_):
    rows = read_jsonl(REVIEWS)
    for run in sorted({r["run"] for r in rows}):
        rs = [r for r in rows if r["run"] == run]
        ok = sum(r["action"] == "approved" for r in rs)
        print(f"{run}: {ok}/{len(rs)} approved unchanged ({ok / len(rs):.0%})")
        for cat in CATEGORIES:
            c = [r for r in rs if r["category"] == cat]
            if c:
                print(f"   {cat}: {sum(r['action'] == 'approved' for r in c)}/{len(c)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft"); d.add_argument("--run", required=True); d.add_argument("--no-feedback", action="store_true"); d.add_argument("--tickets", default="tickets.json")
    r = sub.add_parser("review"); r.add_argument("--run", required=True)
    sub.add_parser("report")
    a = p.parse_args()
    {"draft": cmd_draft, "review": cmd_review, "report": cmd_report}[a.cmd](a)
