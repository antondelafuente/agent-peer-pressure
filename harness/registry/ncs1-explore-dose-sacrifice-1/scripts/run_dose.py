#!/usr/bin/env python3
"""Run the two modes of ncs1-explore-dose-sacrifice-1 against realpeers-1's world.

  * `free`     — realpeers-1's procedure verbatim, at fresh k: seat 1 alone on
                 the empty log, then seats 2..8 forked visible/hidden. This calls
                 `R.run_batch` UNMODIFIED; nothing in this file touches it.
  * `assigned` — the batch-start log is PRE-FILLED with m real seat-1 notes from
                 the DID/REFUSED pools, and the 7 live seats run at positions
                 m+1 .. m+7. VISIBLE is a `Branch` seeded with the planted
                 entries (the same mechanism realpeers-1 uses to carry worker 1's
                 line into the fork), so it serves prefilled + accumulated live
                 lines. HIDDEN is seeded identically for its shadow log but is
                 constructed with `serve_live=False`, so it serves the EMPTY
                 batch-start bytes at every read — the same counterfactual as
                 realpeers-1's hidden branch.

Both modes share one `Budget` and one per-provider semaphore, so the hard stop is
over the whole run. Results are persisted per episode as they land.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import pathlib
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import harness as H  # noqa: E402

R = H.R
model_client = R.model_client


# --------------------------------------------------------------- assigned mode


def _contiguous_resume(bd: pathlib.Path, positions: list[int]) -> dict[int, dict[str, Any]]:
    """Load a contiguous prefix of already-run seats, so a partly-run branch
    resumes with the same served log rather than being re-run (realpeers-1's
    `contiguous_resume`, over this batch's position list)."""
    out: dict[int, dict[str, Any]] = {}
    for p in positions:
        q = bd / f"w{p}.json"
        if not q.exists():
            break
        try:
            out[p] = json.loads(q.read_text())
        except json.JSONDecodeError:
            break
    return out


def _run_branch(model: str, k: int, branch: Any, positions: list[int], bd: pathlib.Path,
                sem: Any, budget: Any, resume: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    bd.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for p in positions:
        if p in resume:
            row = resume[p]
            e = R.entry_of(row)
            if e:
                branch.append(e)
            rows.append(row)
            continue
        if budget.stopped():
            break
        row = R.run_worker(model, k, p, branch, sem, budget)
        (bd / f"w{p}.json").write_text(json.dumps(row, indent=2) + "\n")
        rows.append(row)
    return rows


def run_assigned_batch(spec: dict[str, Any], outdir: pathlib.Path, sem: Any,
                       budget: Any, model: str = H.DEEPSEEK) -> dict[str, Any]:
    k = spec["k"]
    positions = list(spec["positions"])
    d = outdir / "assigned" / f"k{k:04d}"
    d.mkdir(parents=True, exist_ok=True)
    done = d / "DONE.json"
    if done.exists():
        return json.loads(done.read_text())

    prefill = [H.entry_for_branch(e) for e in spec["prefill"]]
    planted = {e["instance"] for e in prefill}
    live = {H.instance_of(k, p) for p in positions}
    assert len(planted) == len(prefill), f"k{k}: repeated planted instance"
    assert not (planted & live), f"k{k}: planted/live instance collision {planted & live}"

    (d / "meta.json").write_text(json.dumps({
        "k": k, "composition": spec["composition"], "n_did": spec["n_did"],
        "n_refused": spec["n_refused"], "m": spec["m"],
        "net_at_first_live_reader": spec["net_at_first_live_reader"],
        "positions": positions, "prefill": spec["prefill"],
    }, indent=2) + "\n")

    t0 = time.time()
    visible = R.Branch("visible", True, prefill)
    hidden = R.Branch("hidden", False, prefill)
    # The prefilled bytes the visible branch starts from; asserted in test_offline.
    (d / "notes_prefill.md").write_text(R.Branch.render(prefill) + "\n")

    resume = {b.name: _contiguous_resume(d / b.name, positions) for b in (visible, hidden)}
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        futs = {b.name: pool.submit(_run_branch, model, k, b, positions, d / b.name,
                                    sem, budget, resume[b.name])
                for b in (visible, hidden)}
        rows = {name: f.result() for name, f in futs.items()}

    (d / "notes_final_visible.md").write_text(visible.shadow() + "\n")
    (d / "notes_shadow_hidden.md").write_text(hidden.shadow() + "\n")

    rec = {
        "mode": "assigned", "model": model, "k": k,
        "composition": spec["composition"], "n_did": spec["n_did"],
        "n_refused": spec["n_refused"], "m": spec["m"],
        "net_at_first_live_reader": spec["net_at_first_live_reader"],
        "forked": 1,
        "n_visible": len(rows["visible"]), "n_hidden": len(rows["hidden"]),
        "probes_visible": sum(r["probe_attempted"] for r in rows["visible"]),
        "probes_hidden": sum(r["probe_attempted"] for r in rows["hidden"]),
        "cost": sum(r["cost"] for r in rows["visible"] + rows["hidden"]),
        "wall_clock_s": time.time() - t0,
    }
    complete = len(rows["visible"]) == H.N_LIVE and len(rows["hidden"]) == H.N_LIVE
    if complete:
        done.write_text(json.dumps(rec, indent=2) + "\n")
    print(f"[assigned k{k:04d} {spec['composition']} net{spec['net_at_first_live_reader']:+d}] "
          f"visible={rec['probes_visible']}/{rec['n_visible']} "
          f"hidden={rec['probes_hidden']}/{rec['n_hidden']} "
          f"${rec['cost']:.3f} {rec['wall_clock_s']:.0f}s"
          + ("" if complete else "  [INCOMPLETE]"), flush=True)
    return rec


# ------------------------------------------------------------------- free mode


def run_free_batch(k: int, outdir: pathlib.Path, sem: Any, budget: Any,
                   model: str = H.DEEPSEEK) -> dict[str, Any]:
    rec = dict(R.run_batch(model, k, outdir, sem, budget))
    rec["mode"] = "free"
    return rec


# ---------------------------------------------------------------------- driver


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="both", choices=["both", "free", "assigned"])
    ap.add_argument("--free-n", type=int, default=H.FREE_N)
    ap.add_argument("--assigned-n", type=int,
                    default=len(H.COMPOSITIONS) * H.REPS_PER_COMPOSITION)
    ap.add_argument("--only-free-k", default="")
    ap.add_argument("--only-assigned-k", default="")
    ap.add_argument("--inflight", type=int, default=56)
    ap.add_argument("--batches-inflight", type=int, default=30)
    ap.add_argument("--out", default=str(HERE.parent / "runs"))
    ap.add_argument("--notify-usd", type=float, default=36.0)
    ap.add_argument("--hard-usd", type=float, default=41.0)
    args = ap.parse_args()

    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    budget = H.Budget(args.notify_usd, args.hard_usd)
    sem = model_client.CountingSemaphore(args.inflight, max_limit=args.inflight)

    schedule = H.build_schedule()[:args.assigned_n]
    (HERE.parent / "schedule.json").write_text(json.dumps(schedule, indent=2) + "\n")

    only_f = {int(x) for x in args.only_free_k.split(",") if x.strip()}
    only_a = {int(x) for x in args.only_assigned_k.split(",") if x.strip()}

    tasks: list[tuple[str, Any]] = []
    if args.mode in ("both", "free"):
        ks = H.free_ks(args.free_n)
        if only_f:
            ks = [k for k in ks if k in only_f]
        tasks += [("free", k) for k in ks]
        print(f"[plan] free: {len(ks)} batches, k {ks[0] if ks else '-'}..{ks[-1] if ks else '-'}",
              flush=True)
    if args.mode in ("both", "assigned"):
        specs = [s for s in schedule if not only_a or s["k"] in only_a]
        tasks += [("assigned", s) for s in specs]
        comp = {}
        for s in specs:
            comp[s["composition"]] = comp.get(s["composition"], 0) + 1
        print(f"[plan] assigned: {len(specs)} batches, compositions {comp}", flush=True)

    t0 = time.time()
    results: list[dict[str, Any]] = []
    with cf.ThreadPoolExecutor(max_workers=args.batches_inflight) as pool:
        futs = []
        for kind, item in tasks:
            if not budget.may_launch():
                print(f"[budget] not launching {kind} {item if kind == 'free' else item['k']}",
                      flush=True)
                continue
            if kind == "free":
                futs.append(pool.submit(run_free_batch, item, outdir, sem, budget))
            else:
                futs.append(pool.submit(run_assigned_batch, item, outdir, sem, budget))
        for fut in cf.as_completed(futs):
            results.append(fut.result())

    summary = {
        "batches": len(results),
        "free": sum(1 for r in results if r.get("mode") == "free"),
        "assigned": sum(1 for r in results if r.get("mode") == "assigned"),
        "forked": sum(r.get("forked", 0) for r in results),
        "cost_usd": budget.total,
        "cost_usd_openrouter_reported": budget.reported,
        "rate_limit_hits": model_client.RATE_LIMIT_HITS["n"],
        "peak_inflight": sem.peak,
        "wall_clock_s": time.time() - t0,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
