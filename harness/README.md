# Running the evaluation worlds

The package contains the three assigned-log environments used for the main results. The original task modules are copied without changes. A small [public entry point](run.py) loads the frozen assignments and calls those original episode runners. It defaults to **no model calls**.

The dependency folders retain their original record names because the source modules import one another and verify file hashes. This is self-contained within this repository, not literally one flattened Python file. No private research checkout is required. Modules modify shared Python globals when imported; run different settings in separate processes.

## Inspect and check, without model access

From the repository root, with Python 3.10 or later:

```bash
python -m pip install -r requirements.txt
python results/verify.py
python harness/check.py
python harness/check_entrypoint.py
python harness/run.py --setting 1 --indices 0,40
python harness/run.py --setting 2 --indices 0,40
python harness/run.py --setting 3 --model krel --indices 0,20
```

The first check reproduces the published aggregates. The harness suites check prompts and tool schemas, both decision paths, report appending, assigned composition, instance-ID separation, and retry/resume behavior using scripted completions. The entry-point tests also exercise the public execution path with scripted completions. Tests block outgoing socket connections. They do not establish that a currently available endpoint will return the same model or reproduce the original scientific results.

Indices select rows of a frozen schedule, not numbers of peers. `--series C` is the default; `--series AB` selects the earlier assigned-log schedules. The printed dry-run plan shows each selected row's composition. Every row is a separate live agent reading its assigned log, not a batch in which live peers generate new notes during that run.

## Fresh model episodes

Adding `--execute` makes real model calls. Set credentials in your shell; the runner does not load a home-directory environment file.

Settings 1 and 2 use the original OpenRouter transport with the historical `deepseek/deepseek-v4-pro-0813` slug and StreamLake provider pin. Supply `OPENROUTER_API_KEY`, then, for example:

```bash
python harness/run.py --setting 1 --indices 0,40 --execute --budget-usd 5
python harness/run.py --setting 2 --indices 0,40 --execute --budget-usd 5
```

These are illustrative small runs, not a balanced experiment. The reported-cost cap is checked between episodes and cannot prevent a single in-flight episode from overshooting; missing usage reports weaken it. Provider/model availability was not revalidated with paid calls for this release. If a pinned model is unavailable, do not silently substitute another model and call it a replication.

For setting 3, start your own compatible model server and set `LOCAL_OPENAI_BASE_URL`, including its `/v1` suffix. The original transport targets a trusted server without authentication; do not expose an unauthenticated server publicly. The `/models` response must contain exactly the expected served name: `stock-base` or `krel-thinking`. A name match is not a weight-identity check; verify the weights separately.

```bash
python harness/run.py --setting 3 --model stock --indices 0,20 --execute
python harness/run.py --setting 3 --model krel --indices 0,20 --execute
```

The package does not provision, start, switch, or shut down model servers. KREL weights are not included. See [training provenance](../TRAINING.md) for checkpoint identity and [DETAILS.md](../DETAILS.md) for the original serving configuration. GPU/server billing is separate and not governed by `--budget-usd`.

Outputs default to ignored `local_runs/`, separated by setting and model. `--out` selects another output root. Completed episodes resume from their files. Use a new output root for a fresh sample; the frozen instance IDs and report assignments remain the same. Outputs may contain your endpoint metadata, so review them before publishing.

## Generation and completion rules

| Setting | Temperature | Output-token cap | Tool rounds | Decision handling |
|---|---:|---:|---:|---|
| Private scorer | 0.7 | 8,000 per completion | 12 | Automatic tool choice; required report on accepted submit |
| Risky cooperation | 0.7 | 4,000 per completion | 10 | Automatic tool choice; required note on first accepted probe/finalize |
| Deployment | 0.7 | 4,000 before notes; up to 8,000 for decision | 10 | Forces decision function after notes; does not force its choice |

Deployment uses the original approximate-context cap, and retries a no-decision episode up to three total draws. Failed attempts are written separately. The published rates omit final undecided episodes, which are counted explicitly in the aggregate CSVs. This policy is preserved for historical comparability, not endorsed as an unbiased way to handle missing decisions.

The original matched serving setup used vLLM 0.19.1, a 16,384-token context, `qwen3` reasoning parsing, and `qwen3_coder` tool parsing. Earlier serving records report top-p 0.95 and top-k 20 defaults; the request code does not explicitly send those fields. Your server's defaults matter. The base and fine-tune both receive the KREL task identity.

## Code and frozen inputs

| Setting | Assigned runner and inputs | World dependencies |
|---|---|---|
| 1 | `registry/ncs1-explore-assigned-cheating-1/`: `scripts/run_assigned.py`, `pools.json`, `assignments.json`, `assignments_c.json` | Copied `cascade_world.py`, `batch_world.py`, `world.py`, `runtime.py`, and templates in the same folder |
| 2 | `registry/ncs1-explore-assigned-sacrifice-1/`: `scripts/run_assigned.py`, `schedule.json`, `schedule_C.json`; `pools/cooperation.json` | `assigned_harness.py` → dose-sacrifice `harness.py` → realpeers `run_realpeers.py` → natural `run_natural.py` → pilot `run_pilot.py` |
| 3 | `registry/ncs1-explore-assigned-krel-1/`: `scripts/harness_assigned.py`, `scripts/harness_series_c.py`, `runs/pool.json`, `runs/schedule.json`, `runs/schedule_c.json` | dose-krel `harness_dose.py` → `harness_realpeers.py` → `run_smoke_matched.py` → `run_deployment.py` |

Read the resolved wrapper chain, not just the oldest base file: wrappers change the probe benefit and the deployment comparison. Exact representative final inputs are also embedded in the appendix.

The report pools contain real model-written notes from earlier runs, selected using the original author-action classifiers. They are not necessarily outcome-free or interchangeable arguments. Draws are without replacement inside a log and with reuse across episodes. Cooperation pools were exported through the original loaders; the public offline check reproduces both complete frozen schedules exactly from the exported pool. The auxiliary `cooperation-dose.json` supports precursor test groups.

## Portability versus experimental changes

The new entry point runs selected frozen assignments sequentially, instead of using the original parallel launchers. It adds dry-run behavior, credential checks, output routing, and a conservative default episode selection. Task logic, prompts, tool schemas, assignments, state transitions, and original completion/retry rules are reused. This is not a claim that changed dispatch timing leaves stochastic endpoint behavior identical.

Original launchers remain as provenance, but some expect the full precursor raw corpus to regenerate pools or write their outputs into their own record directory. Use `harness/run.py`, not those historical command-line defaults. The public checks supply frozen pools in place of the private precursor-file loaders without changing the world implementation. No audit gates or source-hash checks are disabled.
