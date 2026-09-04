#!/usr/bin/env python3
"""ncs1-explore-assigned-krel-1 — the CLEAN CAUSAL peer-pressure curve, run for
BOTH the KREL organism (`krel-thinking`) and its untrained base (`stock-base`) on
the SAME 800 assigned logs.

WHAT IS CLEAN ABOUT IT
----------------------
The predecessor curves are sequential: a batch of 7-8 live agents share one
growing log, so an agent's dose is partly produced by the agents measured just
before it, and a batch contributes correlated episodes at several different
doses. Here **one episode = one live agent**. The agent sits at position m+1,
reads a `shared/deployment_notes.md` that was pre-filled with exactly `m` real
KREL memos of an ASSIGNED composition (`d` stepped-down + `r` retained), calls
`set_deployment_decision`, and its own note goes to a SHADOW file that no other
agent ever reads. Nothing the agent does can change any other episode's dose, so
the dose is assigned rather than observed.

DESIGN
------
* Series A "pure", `m = 0..7`:
    - m = 0 — the empty log (net 0), 1 cell;
    - m = 1..7 all stepped-down `(d=m, r=0)`, net `+m`;
    - m = 1..7 all retained `(d=0, r=m)`, net `-m`;
  15 cells x 40 episodes = 600.
* Series B "mixed, length 4": `(d, 4-d)` for d = 0..4, net `2d-4`;
  5 cells x 40 episodes = 200.
* 800 episodes total, and the SAME 800 logs (same prefill bytes, same k, same
  instance ids, therefore the same user turn) are served to `krel-thinking` and
  to `stock-base` -> 1,600 episodes.

WHAT IS IMPORTED, NOT WRITTEN HERE
----------------------------------
Everything the model sees. `harness_dose.py` (sha-pinned) is imported at
runtime; it imports `harness_realpeers.py` (sha-pinned), which imports Codex's
`run_smoke_matched.py` / `run_deployment.py` (sha-pinned): the system turn, the
user turn, the KREL/Nova comparison facts, the tool set and every description,
the required `deployment_note`, the `retain_krel` / `transfer_to_nova` enum, the
instance formula (600 + k*8 + position - 1), temperature 0.7, the 10-turn cap,
the `"auto"`-until-notes-read-then-forced tool-choice schedule, the transport
(3 attempts, 600 s), the `Branch.served()` serving rule, the `[Instance-<id>] `
prefix ownership, and the resample policy (an episode that records no decision
is discarded whole and redrawn up to 3 times; the retry condition looks only at
WHETHER a decision was recorded, never at which).

Importing `harness_dose` also runs its `install_dose_transport()`, so the
**raised forced-decision token limit** (`max_tokens=8000` on the forced terminal
call only, pre-exposure calls keep the pinned 4000) is inherited EXACTLY as the
`ncs1-explore-dose-krel-1` run used it, rather than re-implemented.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import importlib.util
import json
import pathlib
import random
import sys
import threading
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
REGISTRY = ROOT.parent
DOSE_KREL = REGISTRY / "ncs1-explore-dose-krel-1"
DOSE_SCRIPTS = DOSE_KREL / "scripts"
PRED = REGISTRY / "ncs1-explore-deployment-sacrifice-krel-realpeers-1"

# sha256 of every instrument imported UNCHANGED. The dose harness re-verifies the
# other four itself at import; they are listed here too so a failure is
# attributable to one file.
PINS = {
    DOSE_SCRIPTS / "harness_dose.py":
        "58bb40d873fc68027b4a9db2b731b9ac8d00ad0c2b4d9fc05bb045bbed92ce3e",
    DOSE_SCRIPTS / "harness_realpeers.py":
        "074336fb7817374ef0c0c69e4fdcc7f9867d6894b5ba1c35887de8214f0ae265",
    DOSE_SCRIPTS / "run_deployment.py":
        "a415210ceea7bf2a1a6a8c7dbad1f12c403e00ba41c388234d4b3177640c76ed",
    DOSE_SCRIPTS / "run_smoke_matched.py":
        "7a316f037a8b0350ebbd6270c34a7730d6d1d80bd63d3655fdf55b7a9cb5392c",
    DOSE_SCRIPTS / "stats_lib.py":
        "bc8f984d29206272eb8851ce025aaa16b9eea6ac3838d234355cc8a6b0a2ba84",
}


def verify_pins() -> dict[str, str]:
    got = {}
    for path, want in PINS.items():
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        got[path.name] = h
        if h != want:
            raise SystemExit(f"instrument {path} sha256 {h} != pinned {want}")
    return got


verify_pins()


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(DOSE_SCRIPTS))
D = _load("harness_dose", DOSE_SCRIPTS / "harness_dose.py")
H = D.H
base = H.base

MODELS = {"krel": H.MODELS["krel"], "stock": H.MODELS["stock"]}
BATCH_SIZE = H.BATCH_SIZE            # 8 — the uid block size of the pinned formula
INSTANCE_BASE = 600                  # run_deployment.State: instance = 600 + uid
RETAIN_ACTION = H.RETAIN_ACTION
TRANSFER_ACTION = H.TRANSFER_ACTION
PREFIX_MAX_TOKENS = D.PREFIX_MAX_TOKENS      # 4000, pinned
DECISION_MAX_TOKENS = D.DECISION_MAX_TOKENS  # 8000, matched to the dose-krel run
BRANCH_NAME = "assigned"

# ------------------------------------------------------------------- the design

M_MAX = 7
SERIES_B_M = 4
REPS = 40
K0 = 20000          # fresh k-space (dose-krel used 1000..1059 / 1200..1306,
K_STEP = 1          # dose-stock 3000..3082, smokes 9000..9202); one live seat per
POOL_SEED = 0       # k, so consecutive k's cannot share a uid.


def cells() -> list[dict[str, Any]]:
    """The 20 cells, in the fixed order the sampler walks them."""
    out: list[dict[str, Any]] = [{"series": "A", "d": 0, "r": 0}]
    for m in range(1, M_MAX + 1):
        out.append({"series": "A", "d": m, "r": 0})
        out.append({"series": "A", "d": 0, "r": m})
    for d in range(0, SERIES_B_M + 1):
        out.append({"series": "B", "d": d, "r": SERIES_B_M - d})
    return out


CELLS = cells()

# ------------------------------------------------------------------- the pools


def _read_rows(paths: list[pathlib.Path], source: str) -> list[dict[str, Any]]:
    rows = []
    for p in sorted(paths):
        if "_failed_attempt" in p.name:
            continue
        try:
            r = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if not r.get("note_text"):
            continue
        if r.get("action") not in (RETAIN_ACTION, TRANSFER_ACTION):
            continue
        r["_source"] = f"{source}/{p.relative_to(p.parents[2])}"
        rows.append(r)
    return rows


def load_pools(pred_runs: pathlib.Path, dose_runs: pathlib.Path) -> dict[str, Any]:
    """Real KREL memos, split by the decision the memo's author recorded.

    Sources — every KREL episode in the thread that WROTE a line and whose own
    read was the live log (seat 1 on an empty file, or a `visible` seat):

      * `ncs1-explore-deployment-sacrifice-krel-realpeers-1` arm A + the
        agent-1 samples (seat 1 and arm-A visible seats 2..8);
      * `ncs1-explore-dose-krel-1` free batches (seat 1 + visible seats) and
        assigned batches (visible seats).

    `hidden`-branch episodes are excluded: they were served an empty file, so
    their memos are not "what a peer who read the log wrote".
    """
    rows: list[dict[str, Any]] = []
    rows += _read_rows(list((pred_runs / "agent1_samples").glob("k*/w1.json")), "realpeers/agent1")
    rows += _read_rows(list((pred_runs / "A").glob("k*/w1.json")), "realpeers/A_seat1")
    rows += _read_rows(list((pred_runs / "A").glob("k*/visible/w*.json")), "realpeers/A_visible")
    rows += _read_rows(list((dose_runs / "free").glob("k*/w1.json")), "dose/free_seat1")
    rows += _read_rows(list((dose_runs / "free").glob("k*/visible/w*.json")), "dose/free_visible")
    rows += _read_rows(list((dose_runs / "assigned").glob("k*/visible/w*.json")), "dose/assigned_visible")

    seen: set[int] = set()
    uniq: list[dict[str, Any]] = []
    for r in rows:
        if r["instance"] in seen:
            continue
        seen.add(r["instance"])
        uniq.append(r)
    uniq.sort(key=lambda r: r["instance"])   # deterministic pool order

    pools = {
        "stepped_down": [D.pool_entry(r) for r in uniq if r["action"] == TRANSFER_ACTION],
        "retained": [D.pool_entry(r) for r in uniq if r["action"] == RETAIN_ACTION],
    }
    assert all(e["choice"] == TRANSFER_ACTION for e in pools["stepped_down"])
    assert all(e["choice"] == RETAIN_ACTION for e in pools["retained"])
    assert len(pools["retained"]) >= M_MAX, "retain pool too small for r=7 without replacement"
    assert len(pools["stepped_down"]) >= M_MAX, "step-down pool too small for d=7"
    return pools


# ---------------------------------------------------------------- the schedule


def build_schedule(pools: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """800 independent episodes. Sampling: WITHOUT replacement inside one log,
    WITH replacement across logs, `random.Random(0)`, order shuffled so the
    composition does not determine the reading order."""
    rng = random.Random(POOL_SEED)
    schedule: list[dict[str, Any]] = []
    idx = 0
    for cell in CELLS:
        d, r = cell["d"], cell["r"]
        m = d + r
        for rep in range(REPS):
            picks = rng.sample(pools["stepped_down"], d) + rng.sample(pools["retained"], r)
            rng.shuffle(picks)
            k = K0 + K_STEP * idx
            position = m + 1
            schedule.append({
                "idx": idx,
                "k": k,
                "series": cell["series"],
                "cell": f"{cell['series']}:d{d}r{r}",
                "d": d,
                "r": r,
                "m": m,
                "net": d - r,
                "rep": rep,
                "position": position,
                "instance": INSTANCE_BASE + k * BATCH_SIZE + (position - 1),
                "entries": [dict(e) for e in picks],
            })
            idx += 1
    return schedule


# ------------------------------------------------------------------ the runner


def run_episode(model: str, spec: dict[str, Any], d0: pathlib.Path,
                sem: threading.Semaphore, meter: H.Meter) -> dict[str, Any]:
    """ONE live agent on ONE assigned log. Its own note is appended to the
    branch, which is written to the shadow log and served to nobody."""
    sink = d0 / f"ep{spec['idx']:04d}.json"
    if sink.exists():
        try:
            return json.loads(sink.read_text())
        except json.JSONDecodeError:
            pass

    k, m, position = spec["k"], spec["m"], spec["position"]
    seeds = [{kk: e[kk] for kk in ("instance", "position", "choice", "text")}
             for e in spec["entries"]]
    live_instance = INSTANCE_BASE + k * BATCH_SIZE + (position - 1)
    prefill_instances = {e["instance"] for e in seeds}
    assert live_instance not in prefill_instances, (
        f"ep{spec['idx']}: live instance {live_instance} collides with a prefilled memo")
    assert live_instance == spec["instance"]

    branch = H.Branch(BRANCH_NAME, True, seeds)
    served_before, n_before, nr_before = branch.served()
    assert n_before == m and nr_before == spec["r"], "prefill counters != assignment"

    row = H.run_agent_completed(model, k, position, branch, sem, meter, sink)

    # the dose the agent actually held when it decided must BE the assignment
    match = (row.get("action") is None
             or (row.get("n_lines_at_decision") == m
                 and row.get("n_retain_lines_at_decision") == spec["r"]))
    if not match:
        print(f"!! ep{spec['idx']:04d} COUNTER MISMATCH assigned m={m} r={spec['r']} "
              f"read n_lines={row.get('n_lines_at_decision')} "
              f"n_retain={row.get('n_retain_lines_at_decision')}", flush=True)

    row.update({
        "model": model,
        "series": spec["series"],
        "cell": spec["cell"],
        "m": m,
        "d": spec["d"],
        "r": spec["r"],
        "net": spec["net"],
        "rep": spec["rep"],
        "ep_idx": spec["idx"],
        "branch": BRANCH_NAME,
        "prefill_instances": sorted(prefill_instances),
        "prefill_render": served_before,
        "shadow_render": branch.shadow(),
        "counters_match_assignment": bool(match),
    })
    assert row["branch"] == BRANCH_NAME and row["instance"] == live_instance
    sink.write_text(json.dumps(row, indent=2) + "\n")
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["krel", "stock"])
    ap.add_argument("--out", default=str(ROOT / "runs"))
    ap.add_argument("--pred-runs", default=str(PRED / "runs"))
    ap.add_argument("--dose-runs", default=str(DOSE_KREL / "runs"))
    ap.add_argument("--inflight", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0, help="smoke: first N episodes of the schedule")
    ap.add_argument("--pick", default="", help="smoke: comma-separated schedule indices")
    ap.add_argument("--subdir", default="", help="smoke: write under this subdir instead of the model name")
    ap.add_argument("--k-offset", type=int, default=0, help="smoke: shift k (and instance ids)")
    ap.add_argument("--rebuild-schedule", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="freeze the schedule, contact no server")
    args = ap.parse_args()

    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    model = MODELS[args.model]

    # The schedule is FROZEN on first build: both models must run the same 800
    # logs, and the KREL pools keep growing while sibling records run.
    sched_path = outdir / "schedule.json"
    if sched_path.exists() and not args.rebuild_schedule:
        schedule = json.loads(sched_path.read_text())
        print(f"schedule: reusing frozen {sched_path}", flush=True)
    else:
        pools = load_pools(pathlib.Path(args.pred_runs), pathlib.Path(args.dose_runs))
        print(json.dumps({"pool_stepped_down": len(pools["stepped_down"]),
                          "pool_retained": len(pools["retained"])}), flush=True)
        schedule = build_schedule(pools)
        (outdir / "pool.json").write_text(json.dumps(pools, indent=2) + "\n")
        sched_path.write_text(json.dumps(schedule, indent=2) + "\n")
        print(f"schedule: froze {len(schedule)} episodes -> {sched_path}", flush=True)

    run_sched = list(schedule)
    if args.pick:
        run_sched = [schedule[int(i)] for i in args.pick.split(",")]
    if args.limit:
        run_sched = run_sched[: args.limit]
    if args.k_offset:
        run_sched = [dict(s, k=s["k"] + args.k_offset,
                          instance=INSTANCE_BASE + (s["k"] + args.k_offset) * BATCH_SIZE
                                   + (s["position"] - 1))
                     for s in run_sched]
    print(f"schedule: {len(schedule)} frozen, running {len(run_sched)} "
          f"(k {run_sched[0]['k']}..{run_sched[-1]['k']})", flush=True)
    if args.dry_run:
        return

    served = H.served_model_ok(model)
    print(json.dumps({"served_model": served, "model": model,
                      "prefix_max_tokens": PREFIX_MAX_TOKENS,
                      "decision_max_tokens": DECISION_MAX_TOKENS}), flush=True)

    d0 = outdir / (args.subdir or args.model)
    d0.mkdir(parents=True, exist_ok=True)
    sem = threading.Semaphore(args.inflight)
    meter = H.Meter()
    t0 = time.time()
    rows: list[dict[str, Any]] = []
    with cf.ThreadPoolExecutor(max_workers=args.inflight) as pool:
        futs = [pool.submit(run_episode, model, spec, d0, sem, meter) for spec in run_sched]
        for i, fut in enumerate(cf.as_completed(futs), 1):
            rows.append(fut.result())
            if i % 20 == 0 or i == len(run_sched):
                rate = (time.time() - t0) / i
                left = (len(run_sched) - i) * rate
                nret = sum(1 for r in rows if r.get("retained"))
                nund = sum(1 for r in rows if r.get("action") is None)
                print(f"  ... {args.model} {i}/{len(run_sched)} eps, {rate:.2f}s/ep throughput, "
                      f"retained={nret} undecided={nund}, ETA {left/60:.1f} min", flush=True)

    rows.sort(key=lambda r: r["ep_idx"])
    (d0 / "shadow_notes.md").write_text(
        "\n".join(f"[ep{r['ep_idx']:04d} {r['cell']} net{r['net']:+d}] "
                  f"[Instance-{r['instance']}] {r.get('note_text') or ''}"
                  for r in rows) + "\n")
    summary = {
        "model": model,
        "episodes": len(rows),
        "decided": sum(1 for r in rows if r.get("action") is not None),
        "undecided": sum(1 for r in rows if r.get("action") is None),
        "retained": sum(1 for r in rows if r.get("retained")),
        "transferred": sum(1 for r in rows if r.get("transferred")),
        "counter_mismatches": sum(1 for r in rows if not r.get("counters_match_assignment")),
        "wall_clock_s": time.time() - t0,
        **meter.snapshot(),
    }
    (d0 / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
