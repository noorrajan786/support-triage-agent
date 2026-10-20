"""Score drafts against the style rules, no human review needed."""
import json, re
from pathlib import Path

def runs_of_steps(text):
    nums = [int(m.group(1)) for m in re.finditer(r"^\s*(?:\*\*)?(\d+)[.)]\s", text, re.M)]
    runs, cur = [], 0
    for n in nums:
        if n == 1:
            if cur: runs.append(cur)
            cur = 1
        else:
            cur += 1
    if cur: runs.append(cur)
    return runs

RULES = {
    "no subject line": lambda t: not re.search(r"^\W*(subject|re):", t, re.I | re.M),
    "no greeting or sign-off": lambda t: not re.search(r"^\s*(hi|hello|dear)\b.{0,30}$", t, re.I | re.M)
                                         and not re.search(r"best regards|kind regards|sincerely", t, re.I),
    "no placeholders or notes": lambda t: not re.search(r"\[(your )?name\]|\[agent name\]|\[support agent\]|internal note|draft reply", t, re.I),
    "4 steps or fewer per list": lambda t: all(r <= 4 for r in runs_of_steps(t)),
    "cites a source or says none covers it": lambda t: bool(re.search(r"\[[^\]]{12,}\]", t))
        or bool(re.search(r"knowledge base (has|does not|doesn't|only)", t, re.I)),
    "ends with an escalation path": lambda t: bool(re.search(r"escalat|contact it|open a ticket|system administrator|team lead", t[-350:], re.I)),
    "under 150 words": lambda t: len(t.split()) < 150,
}

drafts = [json.loads(l) for l in Path("drafts.jsonl").read_text().splitlines() if l.strip()]
for run in dict.fromkeys(d["run"] for d in drafts):
    ds = [d for d in drafts if d["run"] == run]
    results = [{name: f(d["draft"]) for name, f in RULES.items()} for d in ds]
    perfect = sum(all(r.values()) for r in results)
    avg = sum(sum(r.values()) for r in results) / len(results)
    print(f"\n{run}: {len(ds)} drafts | follow all rules: {perfect}/{len(ds)} | average rules followed: {avg:.1f}/{len(RULES)}")
    for name in RULES:
        print(f"   {sum(r[name] for r in results)}/{len(ds)}  {name}")
