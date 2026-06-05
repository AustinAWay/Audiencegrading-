# Scoring

Each follower is rated 0–100 by its own Claude Haiku call ("sub-agent") against
a five-criterion rubric. The per-follower totals are averaged into the audience
score.

## The rubric

Defined in [`nichefit/config.py`](../nichefit/config.py) as the `RUBRIC` object —
the single source of truth. Its text is rendered into the Haiku prompt verbatim,
so **editing the bands here changes how the model scores**.

| # | Criterion | Max | What it measures |
|---|-----------|-----|------------------|
| 1 | Niche Relevance | 35 | How clearly the follower belongs to / creates about / engages with the niche (bio, latest tweet, links). |
| 2 | Influence & Reach | 25 | `followers_count` (log-scaled), `listed_count`, `verified`. |
| 3 | Authority / Expertise | 20 | Credentials, affiliations, named recognition. Informed by the optional web lookup. |
| 4 | Engagement Quality | 10 | Latest-tweet resonance **relative to** follower count (likes/RTs per follower). |
| 5 | Account Authenticity / Activity | 10 | Account age, follower/following ratio, activity; bot/spam/dormant signals score low. |

**Total** = sum of the five (0–100). **Tiers:** A = 80–100, B = 60–79,
C = 40–59, D = 0–39.

Each criterion has explicit point bands (e.g. Niche Relevance *30–35: a
recognized creator/expert in the niche*). The full bands live in `config.py` and
are reproduced verbatim in the prompt so scoring is consistent across followers.

## Two scores

- **Audience score** — the plain mean of per-follower totals.
- **Influence-weighted score** — a secondary number weighting each follower by
  `log10(followers_count + 1)`, so high-reach followers count for more.

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

## Optional external web lookup (cost-gated, default OFF)

For followers who are high-influence but thin on in-profile authority signals,
the engine can call Anthropic's `web_search` tool to fetch external context and
feed a short snippet into that follower's scoring prompt (used for the Authority
criterion). It is gated to the **top 5% by follower count**, **max 20
lookups/run**, and **≥ 25,000 followers** (all in `config.py`). Its added cost is
shown in the estimate, and it **skips gracefully** if the tool isn't available.

## Tuning

1. Edit weights / bands / tiers in `config.py`.
2. Re-run with a small sample (~200) and a known account.
3. Compare the tier distribution and top followers against your own judgment.
4. Iterate, then scale the sample up.
