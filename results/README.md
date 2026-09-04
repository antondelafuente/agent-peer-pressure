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

These counts were re-aggregated from the original episode-level CSVs when the appendix was prepared, with zero discrepancies across 144 cells. The original episode-level CSVs are not included here. Their fingerprints are preserved in [SOURCE_MANIFEST.json](../SOURCE_MANIFEST.json).

## Scope

This release supports inspecting and replotting aggregate results. It does not yet enable replaying the original experiments or independently auditing every raw rollout. No model credentials, infrastructure addresses, or checkpoints are distributed.
