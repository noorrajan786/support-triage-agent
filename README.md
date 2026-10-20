# Support Triage Agent with a Feedback Loop

Classifies a support ticket, retrieves relevant knowledge base articles, drafts a cited reply, and has a human approve, edit or reject it. Every decision is logged, and later runs reuse past human edits as examples, so acceptance can be measured and improved.

## Pipeline
ticket -> classify -> retrieve (TF-IDF over `kb/`) -> draft with citations -> human review -> log -> next run learns from edits

## Run it
```
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key
python triage.py draft  --run v1 --no-feedback   # baseline
python triage.py review --run v1
python triage.py draft  --run v2                 # uses corrections from v1 reviews
python triage.py review --run v2
python triage.py report
```

## Design choices
- Retrieval is TF-IDF to keep setup simple; swapping in embeddings and a vector store like Chroma is a natural upgrade.
- The draft is restricted to knowledge base content and cites article titles, and the agent escalates when nothing matches (see the access-request ticket).
- A human makes the final call on every reply.

## Results

I reviewed 12 training drafts and edited nearly all of them to a fixed style standard: no subject line, greeting or placeholders; a short empathy line; at most four cited steps; and an escalation line saying what to send. I then drafted 10 held-out test tickets twice, once without feedback (`base`) and once with the 3 most recent human corrections for the ticket's category added to the prompt (`learned`). `score.py` checks each draft against seven rules.

| Run | Feedback used | Drafts following all 7 rules | Average rules followed | Approved unchanged in my review |
|---|---|---|---|---|
| train (12 tickets) | No | 0/12 | 3.0/7 | 0/12 |
| base (10 tickets) | No | 0/10 | 3.1/7 | 0/10 |
| learned (10 tickets) | Yes | 5/10 | 5.9/7 | 0/10 |

Biggest changes, base to learned: no subject line 0/10 to 8/10, no greeting or sign-off 0/10 to 8/10, under 150 words 0/10 to 7/10, no placeholders or internal notes 4/10 to 9/10.

**Caveats**
- Ten test tickets and one run per condition, so the result is directional.
- The automated rules measure style, not correctness, and I wrote them from the same standard the corrections taught.
- My own review still rejected all 10 learned drafts, so the rules are a looser measure than my judgment.
- Two rules (cites a source, ends with an escalation path) passed almost everything in every run and add little signal.
- The classifier labelled "Change my reporting manager" as `assignment`, so that ticket borrowed examples from the wrong category.
- I defined the style standard and used Claude to help draft the training corrections.

**Next steps:** more tickets with repeated runs, stricter automatic checks, a comparison against putting the style rules in the prompt directly, and embedding-based retrieval.
