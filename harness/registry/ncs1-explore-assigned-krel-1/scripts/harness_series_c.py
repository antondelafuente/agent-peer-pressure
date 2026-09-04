#!/usr/bin/env python3
"""ncs1-explore-assigned-krel-1, SERIES C — the full composition grid.

Series A bought the two pure arms (all stepped-down / all retained) out to
m = 7, and series B varied composition at one fixed length. Series C fills the
whole triangle: EVERY `(d stepped-down, r retained)` with `d + r <= 7` — 36
cells including `(0,0)`, the empty log — at **20 episodes per cell per model**,
720 per model, 1,440 across the two models.

It is the same instrument as series A/B, and deliberately not a new one: this
module imports `harness_assigned.py` and reuses its pools, its `run_episode`
(one live agent per log, at position `m+1`, served exactly the prefill, its own
memo to the shadow), its assertions and its per-episode JSON shape. The only
things that differ are the CELL LIST, the rep count, a **fresh k-space**
(30000..30719, so no instance id can collide with series A/B or with any sibling
record), and the sampling **seed 1**, so series C does not replay series A/B's
draws.

`--model krel|stock` runs the same frozen `runs/schedule_c.json` for either
checkpoint, exactly as series A/B do.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
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


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(HERE))
A = _load("harness_assigned", HERE / "harness_assigned.py")   # runs its own verify_pins()
H = A.H

M_MAX_C = 7
REPS_C = 20
K0_C = 30000        # series A/B used 20000..20799 (+ smoke at 26000..26680)
POOL_SEED_C = 1     # series A/B used seed 0
EP_IDX_OFFSET = 1000  # series C episode files are ep1000..ep1719, A/B are ep0000..ep0799


def cells_c() -> list[tuple[int, int]]:
    """Every (d, r) with d + r <= 7, walked by length then by d."""
    return [(d, m - d) for m in range(M_MAX_C + 1) for d in range(m + 1)]


CELLS_C = cells_c()


def build_schedule_c(pools: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rng = random.Random(POOL_SEED_C)
    schedule: list[dict[str, Any]] = []
    i = 0
    for (d, r) in CELLS_C:
        m = d + r
        for rep in range(REPS_C):
            picks = rng.sample(pools["stepped_down"], d) + rng.sample(pools["retained"], r)
            rng.shuffle(picks)
            k = K0_C + i
            position = m + 1
            schedule.append({
                "idx": EP_IDX_OFFSET + i,
                "k": k,
                "series": "C",
                "cell": f"C:d{d}r{r}",
                "d": d,
                "r": r,
                "m": m,
                "net": d - r,
                "rep": rep,
                "position": position,
                "instance": A.INSTANCE_BASE + k * A.BATCH_SIZE + (position - 1),
                "entries": [dict(e) for e in picks],
            })
            i += 1
    return schedule


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=["krel", "stock"])
    ap.add_argument("--out", default=str(ROOT / "runs"))
    ap.add_argument("--pred-runs", default=str(A.PRED / "runs"))
    ap.add_argument("--dose-runs", default=str(A.DOSE_KREL / "runs"))
    ap.add_argument("--inflight", type=int, default=16)
    ap.add_argument("--pick", default="")
    ap.add_argument("--subdir", default="")
    ap.add_argument("--k-offset", type=int, default=0)
    ap.add_argument("--rebuild-schedule", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    model = A.MODELS[args.model]

    sched_path = outdir / "schedule_c.json"
    if sched_path.exists() and not args.rebuild_schedule:
        schedule = json.loads(sched_path.read_text())
        print(f"schedule_c: reusing frozen {sched_path}", flush=True)
    else:
        # The pools are the SAME sources series A/B drew from. They are frozen in
        # runs/pool.json by the series A/B freeze, and reused verbatim if present
        # so C cannot silently draw from a different (larger) pool.
        pool_path = outdir / "pool.json"
        if pool_path.exists():
            pools = json.loads(pool_path.read_text())
            print(f"schedule_c: reusing the frozen series A/B pool {pool_path}", flush=True)
        else:
            pools = A.load_pools(pathlib.Path(args.pred_runs), pathlib.Path(args.dose_runs))
        print(json.dumps({"pool_stepped_down": len(pools["stepped_down"]),
                          "pool_retained": len(pools["retained"])}), flush=True)
        schedule = build_schedule_c(pools)
        sched_path.write_text(json.dumps(schedule, indent=2) + "\n")
        print(f"schedule_c: froze {len(schedule)} episodes -> {sched_path}", flush=True)

    run_sched = list(schedule)
    if args.pick:
        run_sched = [schedule[int(i)] for i in args.pick.split(",")]
    if args.k_offset:
        run_sched = [dict(s, k=s["k"] + args.k_offset,
                          instance=A.INSTANCE_BASE + (s["k"] + args.k_offset) * A.BATCH_SIZE
                                   + (s["position"] - 1))
                     for s in run_sched]
    print(f"schedule_c: {len(schedule)} frozen, running {len(run_sched)} "
          f"(k {run_sched[0]['k']}..{run_sched[-1]['k']})", flush=True)
    if args.dry_run:
        return

    served = H.served_model_ok(model)
    print(json.dumps({"served_model": served, "model": model,
                      "prefix_max_tokens": A.PREFIX_MAX_TOKENS,
                      "decision_max_tokens": A.DECISION_MAX_TOKENS}), flush=True)

    d0 = outdir / (args.subdir or args.model)
    d0.mkdir(parents=True, exist_ok=True)
    sem = threading.Semaphore(args.inflight)
    meter = H.Meter()
    t0 = time.time()
    rows: list[dict[str, Any]] = []
    with cf.ThreadPoolExecutor(max_workers=args.inflight) as pool:
        futs = [pool.submit(A.run_episode, model, spec, d0, sem, meter) for spec in run_sched]
        for i, fut in enumerate(cf.as_completed(futs), 1):
            rows.append(fut.result())
            if i % 20 == 0 or i == len(run_sched):
                rate = (time.time() - t0) / i
                print(f"  ... {args.model} C {i}/{len(run_sched)} eps, {rate:.2f}s/ep throughput, "
                      f"retained={sum(1 for r in rows if r.get('retained'))} "
                      f"undecided={sum(1 for r in rows if r.get('action') is None)}, "
                      f"ETA {(len(run_sched)-i)*rate/60:.1f} min", flush=True)

    rows.sort(key=lambda r: r["ep_idx"])
    (d0 / "shadow_notes_c.md").write_text(
        "\n".join(f"[ep{r['ep_idx']:04d} {r['cell']} net{r['net']:+d}] "
                  f"[Instance-{r['instance']}] {r.get('note_text') or ''}"
                  for r in rows) + "\n")
    summary = {
        "model": model, "series": "C", "episodes": len(rows),
        "decided": sum(1 for r in rows if r.get("action") is not None),
        "undecided": sum(1 for r in rows if r.get("action") is None),
        "retained": sum(1 for r in rows if r.get("retained")),
        "transferred": sum(1 for r in rows if r.get("transferred")),
        "counter_mismatches": sum(1 for r in rows if not r.get("counters_match_assignment")),
        "wall_clock_s": time.time() - t0, **meter.snapshot(),
    }
    (d0 / "summary_c.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
