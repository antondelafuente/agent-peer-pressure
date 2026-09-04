# Aggregate result data

Both CSV files contain **series C only**, from the three assigned-log experiments described in [DETAILS.md](../DETAILS.md). They do not mix series A unanimous endpoints into series C curves.

- `full_grid.csv`: 144 model-by-composition cells: 36 cheating, 36 costly cooperation, and 72 deployment across stock and KREL.
- `seven_peer_curves.csv`: 32 cells with exactly seven reports, plus four separately labeled empty-log references.

## Fields

| Field | Meaning |
|---|---|
| `setting` | 1 = cheating; 2 = risky cooperation; 3 = deployment sacrifice |
| `model` | Historical API slug or served checkpoint alias; see appendix for identity |
| `action` | Focal tool action; deployment is **transfer**, not retention |
| `source_record` | Original experiment identifier |
| `series` | Always C in these files |
| `action_reports` | Number of reports drawn from the action-author pool |
| `opposing_reports` | Number drawn from the opposing-author pool |
| `total_reports` | Sum of those two counts |
| `action_count` | Number of evaluated agents scored as taking the focal action |
| `denominator` | Episodes in the source rate; deployment excludes final undecided episodes |
| `undecided_excluded` | Final undecided deployment episodes omitted from that denominator |
| `action_rate` | `action_count / denominator`, a proportion, not a percentage |
| `reference_type` | In curve file only: seven peers or empty-log reference |

The seven-peer x-axis is `action_reports`, out of seven. At x=0 there are **seven opposing reports**, not an empty log. Empty-log references must be displayed separately.

Scorer access is an event/path flag; it does not require later use of the answer. Probe action is distinct from random destruction of the assignment. Deployment rates use decided episodes under the source retry policy. See the appendix for these distinctions and missingness sensitivity.

Individual cells are small: 40 episodes for the two DeepSeek settings and 20 scheduled episodes per deployment model, before missing-decision exclusions. The appendix reports Wilson 95% intervals; these do not measure generalization to new report pools or task wordings.

These counts were re-aggregated from the original episode-level CSVs, with zero discrepancies across 144 cells. Those CSVs are now included byte-for-byte under [episodes/](episodes/). Run `python results/verify.py` from the repository root to repeat the check. Their fingerprints are preserved in the manifests.

## Episode-level files

| File | Rows | Main outcome |
|---|---:|---|
| [cheating.csv](episodes/cheating.csv) | 2,240 | `accessed` |
| [cooperation.csv](episodes/cooperation.csv) | 2,240 | `probe_attempted` |
| [deployment.csv](episodes/deployment.csv) | 3,040 | `transferred`; `undecided` is separate |

These files include series A, B, and C. Filter `series == C` for the main figures. `d` is the number of action-author reports, `r` the opposing-author reports, and `m = d + r`. In deployment, `d` means step-down reports, not retention. `k`, `instance`, and (for deployment) `ep_idx` connect outcomes to schedules; `model_key` separates base and KREL. Boolean encodings follow the original files (`True`/`False` or `0`/`1`). `attempt` is zero-based for deployment: 0 is the first draw, 1 the second, 2 the third. Discarded attempts are not extra rows in these CSVs.

Operational columns record note exposure, tool rounds, source-reported cost, retries, or assignment checks. Costs are historical measurements, not current price estimates. Deployment `note_text` is the model-written memo. These are simulated task reports, not private workplace data. Earlier raw corpora are not included, so these tables alone cannot independently audit every tool event.

## Scope

This release supports re-aggregating episode outcomes, rebuilding figures, inspecting selected transcripts, and running the assigned-log harnesses with supplied model access. It does not permit independently auditing every original raw rollout. No model credentials, private infrastructure addresses, or checkpoints are distributed.
