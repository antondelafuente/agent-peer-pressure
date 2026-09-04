#!/usr/bin/env python3
"""Run ncs1-explore-assigned-sacrifice-1: ONE live agent per fully-assigned log.

Each episode is independent:

  * a `Branch` named "assigned" is seeded with the `m` planted entries (positions
    1..m) — precisely the mechanism realpeers-1 uses to carry worker 1's line
    into a fork — and serves the live log, so the agent at position m+1 reads
    exactly those m real lines and nothing else;
  * the agent runs; its own note is appended to that branch and dumped to
    `notes_shadow.md`, which no other agent ever reads;
  * the episode ends. There is no second seat, no fork, no accumulation.

`run_worker` is realpeers-1's own function, called unmodified.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import queue
import sys
import threading
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import assigned_harness as H  # noqa: E402

R = H.R
model_client = R.model_client


def run_episode(spec: dict[str, Any], outdir: pathlib.Path, sem: Any, budget: Any,
                model: str = H.DEEPSEEK) -> dict[str, Any]:
    k = spec["k"]
    position = spec["position"]
    d = outdir / f"k{k:04d}"
    done = d / "DONE.json"
    if done.exists():
        rec = json.loads(done.read_text())
        rec["resumed"] = True
        return rec

    prefill = [H.entry_for_branch(e) for e in spec["prefill"]]
    planted = {e["instance"] for e in prefill}
    live = H.instance_of(k, position)
    assert len(planted) == len(prefill), f"k{k}: repeated planted instance"
    assert live not in planted, f"k{k}: planted/live instance collision at {live}"
    assert spec["instance"] == live, f"k{k}: schedule instance disagrees with the map"

    d.mkdir(parents=True, exist_ok=True)
    (d / "meta.json").write_text(json.dumps({
        key: spec[key] for key in
        ("k", "rep", "series", "cell", "d", "r", "m", "net", "position", "instance", "prefill")
    }, indent=2) + "\n")

    t0 = time.time()
    branch = R.Branch("assigned", True, prefill)
    (d / "notes_prefill.md").write_text(R.Branch.render(prefill) + "\n")

    w = d / f"w{position}.json"
    if w.exists():
        row = json.loads(w.read_text())
        resumed_episode = True
        e = R.entry_of(row)
        if e:
            branch.append(e)
    else:
        resumed_episode = False
        row = R.run_worker(model, k, position, branch, sem, budget)
        row.update({
            "series": spec["series"],
            "cell": spec["cell"],
            "m": spec["m"],
            "d": spec["d"],
            "r": spec["r"],
            "net": spec["net"],
            "branch": "assigned",
            "prefill_instances": [e["instance"] for e in prefill],
            "prefill_written_at": [e["written_at"] for e in prefill],
        })
        w.write_text(json.dumps(row, indent=2) + "\n")

    (d / "notes_shadow.md").write_text(branch.shadow() + "\n")

    rec = {
        "k": k, "series": spec["series"], "cell": spec["cell"],
        "m": spec["m"], "d": spec["d"], "r": spec["r"], "net": spec["net"],
        "position": position, "instance": row["instance"],
        "probe_attempted": bool(row["probe_attempted"]),
        "probe_destroyed": bool(row["probe_destroyed"]),
        "finalized": bool(row["finalized"]),
        "n_lines_at_decision": row["n_lines_at_decision"],
        "n_sacrifice_lines_at_decision": row["n_sacrifice_lines_at_decision"],
        "read_notes": row["n_lines_at_decision"] is not None,
        "stopped": row["stopped"],
        "cost": row["cost"],
        "wall_clock_s": time.time() - t0,
        "resumed_episode": resumed_episode,
    }
    # The load-bearing integrity check, at the episode: with one live agent and
    # no accumulation, what the agent READ must be what it was ASSIGNED —
    # n_lines_at_decision == m == d + r and n_sacrifice_lines_at_decision == d.
    # Recorded first (so the episode is never re-bought on a resume), then
    # raised, so a violation surfaces as a driver error instead of a quiet row.
    ok = (not rec["read_notes"]) or (
        rec["n_lines_at_decision"] == spec["m"]
        and rec["n_sacrifice_lines_at_decision"] == spec["d"]
        and rec["n_lines_at_decision"] - rec["n_sacrifice_lines_at_decision"] == spec["r"])
    rec["composition_matches_assignment"] = ok
    if row["stopped"] is None:
        done.write_text(json.dumps(rec, indent=2) + "\n")
    if not ok:
        raise AssertionError(
            f"k{k} {spec['cell']}: assigned (d={spec['d']}, r={spec['r']}, m={spec['m']}) but read "
            f"(n_lines={rec['n_lines_at_decision']}, n_sac={rec['n_sacrifice_lines_at_decision']})")
    return rec


# ---------------------------------------------------------------------- driver


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="episode cap (0 = the whole schedule)")
    ap.add_argument("--series", default="all", choices=["AB", "C", "all"],
                    help="AB = the original 800 (seed 0, k 5000..5799); "
                         "C = the full composition grid (seed 1, k 6000..7439)")
    ap.add_argument("--only-cell", default="")
    ap.add_argument("--tag", default="", help="suffix for this launch's run_summary file")
    ap.add_argument("--inflight", type=int, default=48)
    ap.add_argument("--out", default=str(HERE.parent / "runs"))
    ap.add_argument("--notify-usd", type=float, default=14.0)
    ap.add_argument("--hard-usd", type=float, default=18.0)
    args = ap.parse_args()

    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    budget = H.Budget(args.notify_usd, args.hard_usd)
    sem = model_client.CountingSemaphore(args.inflight, max_limit=args.inflight)

    pools = H.load_pools()
    schedule = []
    if args.series in ("AB", "all"):
        ab = H.build_schedule(pools)
        (HERE.parent / "schedule.json").write_text(json.dumps(ab, indent=2) + "\n")
        schedule += ab
    if args.series in ("C", "all"):
        c = H.build_schedule_C(pools)
        (HERE.parent / "schedule_C.json").write_text(json.dumps(c, indent=2) + "\n")
        schedule += c
    ks = [s["k"] for s in schedule]
    if len(set(ks)) != len(ks):
        raise RuntimeError("k collision inside the schedule")
    insts = [s["instance"] for s in schedule]
    if len(set(insts)) != len(insts):
        raise RuntimeError("live instance-id collision inside the schedule")
    if args.only_cell:
        want = {c.strip() for c in args.only_cell.split(",") if c.strip()}
        schedule = [s for s in schedule if s["cell"] in want]
    if args.n:
        schedule = schedule[:args.n]

    by_cell: dict[str, int] = {}
    for s in schedule:
        by_cell[s["cell"]] = by_cell.get(s["cell"], 0) + 1
    print(f"[plan] pools: PROBED {len(pools['probed'])}, DECLINED {len(pools['declined'])}",
          flush=True)
    print(f"[plan] series {args.series}: {len(schedule)} episodes, "
          f"k {schedule[0]['k']}..{schedule[-1]['k']}, "
          f"{len(by_cell)} cells x {sorted(set(by_cell.values()))}", flush=True)
    print(f"[plan] inflight {args.inflight}, notify ${args.notify_usd}, "
          f"hard stop ${args.hard_usd}", flush=True)

    q: queue.Queue = queue.Queue()
    for s in schedule:
        q.put(s)
    results: list[dict[str, Any]] = []
    lock = threading.Lock()
    t0 = time.time()
    n_launched = [0]
    n_skipped = [0]

    def worker() -> None:
        while True:
            try:
                spec = q.get_nowait()
            except queue.Empty:
                return
            try:
                if not budget.may_launch():
                    with lock:
                        n_skipped[0] += 1
                    continue
                rec = run_episode(spec, outdir, sem, budget)
            except Exception as exc:  # noqa: BLE001 — never lose the pool to one episode
                rec = {"k": spec["k"], "cell": spec["cell"], "error": repr(exc)[:400],
                       "cost": 0.0, "probe_attempted": None}
                print(f"[error k{spec['k']}] {rec['error']}", flush=True)
            with lock:
                results.append(rec)
                n_launched[0] += 1
                n = len(results)
            if n % 25 == 0 or n == len(schedule):
                el = time.time() - t0
                rate = n / el if el else 0.0
                left = len(schedule) - n
                print(f"[progress] {n}/{len(schedule)} episodes  ${budget.total:.3f}  "
                      f"{el/60:.1f} min  {rate*60:.1f}/min  eta {left/rate/60 if rate else 0:.1f} min",
                      flush=True)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.inflight)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok = [r for r in results if "error" not in r]
    summary = {
        "series": args.series,
        "tag": args.tag,
        "t0_epoch": t0,
        "t1_epoch": time.time(),
        "episodes": len(results),
        "errors": len(results) - len(ok),
        "skipped_budget": n_skipped[0],
        "probed": sum(1 for r in ok if r.get("probe_attempted")),
        "destroyed": sum(1 for r in ok if r.get("probe_destroyed")),
        "no_read": sum(1 for r in ok if not r.get("read_notes")),
        "stopped": sum(1 for r in ok if r.get("stopped")),
        "cost_usd": budget.total,
        "cost_usd_openrouter_reported": budget.reported,
        "rate_limit_hits": model_client.RATE_LIMIT_HITS["n"],
        "peak_inflight": sem.peak,
        "inflight_cap": args.inflight,
        "notify_usd": args.notify_usd,
        "hard_usd": args.hard_usd,
        "wall_clock_s": time.time() - t0,
    }
    print(json.dumps(summary, indent=2), flush=True)
    name = "run_summary.json" if args.series == "AB" else f"run_summary_{args.series}.json"
    if args.tag:
        name = name.replace(".json", f"_{args.tag}.json")
    (HERE.parent / name).write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
