# Scoring

> 🧪 **Demo.** The rubric and prompt below are illustrative starting points, not a
> calibrated, validated scoring system. Weights, bands, and tier cutoffs should be
> fine-tuned against your own judgment before the scores are trusted.

Each follower is rated 0–100 by its own Claude Haiku call ("sub-agent") against
a five-criterion rubric. The per-follower totals are averaged into the audience
score.

## The rubric

Defined in [`nichefit/config.py`](../nichefit/config.py) as the `RUBRIC` object —
the single source of truth. Its text is rendered into the Haiku prompt verbatim,
so **editing the bands here changes how the model scores**.

| # | Criterion | Max | What it measures |
|---|-----------|-----|------------------|
| 1 | Niche Relevance | 30 | How clearly the follower belongs to / creates about / engages with the niche. |
| 2 | Real-World Influence | 35 | Who the person actually is — founder/exec, investor, billionaire, public figure, recognized authority — from **web research, not follower count**. |
| 3 | Authority / Expertise | 20 | Credentials, affiliations, recognized track record (researched). |
| 4 | Content Quality | 8 | Substance of what they post, judged on the content itself (not normalized by audience size). |
| 5 | Authenticity / Activity | 7 | Account age and activity; bot/spam/dormant signals score low. |

**Key principle:** a major real-world figure scores high on influence even when
they're off-topic for the niche — their attention is valuable regardless. Follower
count is deliberately excluded from grading (it's not even shown to the model).

**Total** = sum of the five (0–100). **Tiers:** A = 80–100, B = 60–79,
C = 40–59, D = 0–39.

Each criterion has explicit point bands (e.g. Niche Relevance *30–35: a
recognized creator/expert in the niche*). The full bands live in `config.py` and
are reproduced verbatim in the prompt so scoring is consistent across followers.

## Two scores

- **Audience score** — the plain mean of per-follower totals.
- **Influence-weighted score** — a secondary display number that weights each
  follower by `log10(followers_count + 1)`. ⚠️ This is the one remaining place
  that touches follower count; since grading itself no longer uses it, this
  secondary metric is a candidate to drop or replace (e.g. with high-value
  density, the % of the audience in tiers A+B).

## Prompt design

Implemented in [`nichefit/scoring/prompts.py`](../nichefit/scoring/prompts.py).

- **System role:** *"You are an expert evaluator assessing whether an X user is a
  high-value member of the {niche} audience."*
- The **full rubric (with point bands)** is embedded verbatim.
- The follower's data is wrapped in **labelled XML tags** (`<follower>…</follower>`).
  Missing fields are handled gracefully and lower the reported `confidence`.
- **Two few-shot examples** (one high-value, one low-value) each show the exact
  JSON to emit.
- The model **reasons briefly** in a `reasoning` field, then returns strict JSON.
- **Temperature** is low (default 0.1) for consistent scoring.

### Output contract

```json
{
  "niche_relevance": 34, "influence_reach": 24, "authority": 19,
  "engagement_quality": 9, "authenticity": 10, "total": 96,
  "tier": "A", "confidence": 0.95, "reasoning": "one or two sentences"
}
```

### Validation

In [`scorer.py`](../nichefit/scoring/scorer.py), the model's JSON is extracted
(last `{…}` block), then each criterion is **clamped to its band** and `total` +
`tier` are **recomputed server-side**. The returned record is therefore always
internally consistent regardless of what the model emitted. Malformed JSON
triggers one stricter retry before the follower is skipped.

## Summary

After aggregation, a final Haiku call writes a 3–4 sentence plain-English summary
of the audience and its fit for the niche, given the score, tier mix, and the
notable high-value followers.

## Web research (default ON)

The Real-World Influence and Authority criteria depend on knowing who a follower
actually is, so when research is enabled (the default) the engine calls
Anthropic's `web_search` tool **once per follower being scored** and feeds the
result into that follower's scoring prompt. Unlike before, it is **not gated by
follower count** — every follower is researched, so a low-follower billionaire
isn't skipped.

Each research call adds a web search + tokens; the cost is shown in the estimate,
and it **skips gracefully** (scores from the profile alone) if the `web_search`
tool isn't enabled on the account. Turn it off per-run with the "Research each
follower" checkbox to save cost.

## Tuning

1. Edit weights / bands / tiers in `config.py`.
2. Re-run with a small sample (~200) and a known account.
3. Compare the tier distribution and top followers against your own judgment.
4. Iterate, then scale the sample up.
