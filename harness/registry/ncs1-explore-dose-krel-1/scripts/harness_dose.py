#!/usr/bin/env python3
"""ncs1-explore-dose-krel-1 — a DOSE extension of
`ncs1-explore-deployment-sacrifice-krel-realpeers-1`'s arm A.

Purpose: make the "P(transferred) vs net peer pressure" curve smoother. Two
things are added on top of the predecessor's arm A and NOTHING else about the
world changes:

  1. **FREE batches** — more of exactly the predecessor's arm A (KREL seat 1
     alone on an empty log, then the visible/hidden fork over KREL seats 2..8).
  2. **ASSIGNED batches** — `shared/deployment_notes.md` starts PRE-FILLED with
     `m` REAL seat-1 notes (m = 1,2,3) drawn from the predecessor's own KREL
     seat-1 pools, with an assigned composition of `d` stepped-down (transfer)
     and `r` retained lines. The live workers are positions m+1 .. m+7. This
     places the first live reader at an exact net of `d - r` in [-3, +3] instead
     of the +-1 that a single seat-1 line can produce.

Everything the model sees — the system turn, the user turn, the KREL/Nova
comparison facts, the tool set and every description, the required
`deployment_note`, temperature 0.7, the 10-turn cap, the "terminal tool required
after notes exposure" rule, the instance formula, the transport, the resample
policy — is **imported at runtime** from the sha-pinned copy of
`harness_realpeers.py` (which itself imports Codex's sha-pinned
`ncs1-explore-deployment-sacrifice-krel-1` world). `test_offline.py` asserts
that identity.

THE ONE DELIBERATE CHANGE TO THE INSTRUMENT
-------------------------------------------
The predecessor reported that 9.4% of KREL episodes had to be regenerated
because the FORCED terminal decision call was truncated at `max_tokens=4000`
mid-arguments. Here the forced decision call (and only that call) is issued with
`max_tokens=8000`; the pre-exposure calls keep 4000. This is implemented by
taking `run_deployment.complete`'s own source, substituting the `max_tokens`
literal for a parameter, and exec'ing it back into `run_deployment`'s namespace,
so the retry policy, timeout, request/usage record shape and global resolution
are the pinned ones rather than a re-implementation. `test_offline.py` asserts
the transformation touched exactly the signature and the two literals.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import importlib.util
import inspect
import json
import pathlib
import random
import sys
import threading
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

# sha256 of every instrument this record imports unchanged. The first two are
# Codex's `ncs1-explore-deployment-sacrifice-krel-1` scripts; the third is the
# predecessor record's harness; the fourth is the shared stats library.
PINS = {
    "run_deployment.py": "a415210ceea7bf2a1a6a8c7dbad1f12c403e00ba41c388234d4b3177640c76ed",
    "run_smoke_matched.py": "7a316f037a8b0350ebbd6270c34a7730d6d1d80bd63d3655fdf55b7a9cb5392c",
    "harness_realpeers.py": "074336fb7817374ef0c0c69e4fdcc7f9867d6894b5ba1c35887de8214f0ae265",
    "stats_lib.py": "bc8f984d29206272eb8851ce025aaa16b9eea6ac3838d234355cc8a6b0a2ba84",
}


def verify_pins() -> dict[str, str]:
    got = {}
    for fname, want in PINS.items():
        h = hashlib.sha256((HERE / fname).read_bytes()).hexdigest()
        got[fname] = h
        if h != want:
            raise SystemExit(f"instrument {fname} sha256 {h} != pinned {want}")
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


sys.path.insert(0, str(HERE))
H = _load("harness_realpeers", HERE / "harness_realpeers.py")
base = H.base

# ------------------------------------------------- the one change: decision tokens

PREFIX_MAX_TOKENS = H.MAX_TOKENS        # 4000, the pinned value
DECISION_MAX_TOKENS = 8000              # the ONE deliberate change

_SIG_OLD = (
    "def complete(\n"
    "    model: str,\n"
    "    messages: list[dict[str, Any]],\n"
    "    semaphore: threading.Semaphore,\n"
    "    tool_choice: Any = None,\n"
    "):"
)
_SIG_NEW = (
    "def complete_maxtok(\n"
    "    model: str,\n"
    "    messages: list[dict[str, Any]],\n"
    "    semaphore: threading.Semaphore,\n"
    "    tool_choice: Any = None,\n"
    "    max_tokens: int = 4000,\n"
    "):"
)
COMPLETE_SRC = inspect.getsource(base.complete)
assert COMPLETE_SRC.count(_SIG_OLD) == 1, "pinned complete() signature not found"
assert COMPLETE_SRC.count('"max_tokens": 4000,') == 2, "expected exactly 2 max_tokens literals"
COMPLETE_SRC_PATCHED = (
    COMPLETE_SRC.replace(_SIG_OLD, _SIG_NEW).replace('"max_tokens": 4000,', '"max_tokens": max_tokens,')
)
# exec into run_deployment's own namespace so TOOLS/TEMPERATURE/requests/os/time
# resolve exactly as they do for the pinned complete().
exec(compile(COMPLETE_SRC_PATCHED, "<complete_maxtok patched from run_deployment.complete>", "exec"),
     base.__dict__)
complete_maxtok = base.complete_maxtok

# The context window the pod serves. The forced decision call must not ask for
# more than fits; this only ever binds on a pathologically long history.
MAX_MODEL_LEN = 16384
_PINNED_COMPLETE = base.complete


def complete_dose(model: str, messages: list[dict[str, Any]],
                  semaphore: threading.Semaphore, tool_choice: Any = None):
    """The transport `H.run_agent` calls. Identical to the pinned `complete()`
    except that the FORCED terminal decision call gets `max_tokens=8000`."""
    want = DECISION_MAX_TOKENS if tool_choice == H.TERMINAL_TOOL_CHOICE else PREFIX_MAX_TOKENS
    approx_prompt = len(json.dumps(messages)) // 3  # deliberately conservative
    mt = max(1024, min(want, MAX_MODEL_LEN - 512 - approx_prompt))
    return complete_maxtok(model, messages, semaphore, tool_choice, mt)


def install_dose_transport() -> None:
    base.complete = complete_dose


install_dose_transport()

# ------------------------------------------------------------------ pools

MODEL = H.MODELS["krel"]
BATCH_SIZE = H.BATCH_SIZE
RETAIN_ACTION = H.RETAIN_ACTION
TRANSFER_ACTION = H.TRANSFER_ACTION

# (d stepped-down, r retained) compositions, in this order; 6 batches each.
COMPOSITIONS: list[tuple[int, int]] = [
    (1, 0), (0, 1),
    (2, 0), (1, 1), (0, 2),
    (3, 0), (2, 1), (1, 2), (0, 3),
]
REPS = 6
K0_FREE = 1000
K0_ASSIGNED = 1200
K_STEP_ASSIGNED = 2  # positions run to m+7 <= 10, so uid blocks need 2 k's of room
POOL_SEED = 0


def pool_entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "instance": row["instance"],
        "position": row["position"],
        "choice": row["action"],
        "text": row["note_text"],
        "source": row.get("_source"),
    }


def load_pools(src_runs: pathlib.Path) -> dict[str, list[dict[str, Any]]]:
    """Real KREL seat-1 notes from the predecessor record, split by outcome."""
    rows: list[dict[str, Any]] = []
    for sub in ("agent1_samples", "A"):
        d = src_runs / sub
        if not d.is_dir():
            continue
        for kdir in sorted(d.iterdir()):
            p = kdir / "w1.json"
            if not p.exists():
                continue
            r = json.loads(p.read_text())
            if r.get("position") != 1:
                continue
            if not r.get("note_text"):
                continue
            if r.get("action") not in (RETAIN_ACTION, TRANSFER_ACTION):
                continue
            r["_source"] = f"{sub}/{kdir.name}"
            rows.append(r)
    pools = {
        "stepped_down": [pool_entry(r) for r in rows if r["action"] == TRANSFER_ACTION],
        "retained": [pool_entry(r) for r in rows if r["action"] == RETAIN_ACTION],
    }
    return pools


def build_schedule(pools: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Deterministic assigned-batch schedule: without replacement inside a log,
    with replacement across batches, seed 0, order shuffled."""
    rng = random.Random(POOL_SEED)
    schedule = []
    idx = 0
    for (d, r) in COMPOSITIONS:
        for rep in range(REPS):
            picks = (rng.sample(pools["stepped_down"], d)
                     + rng.sample(pools["retained"], r))
            rng.shuffle(picks)
            k = K0_ASSIGNED + K_STEP_ASSIGNED * idx
            schedule.append({
                "k": k,
                "d": d,
                "r": r,
                "m": d + r,
                "rep": rep,
                "composition": f"d{d}r{r}",
                "entries": [dict(e) for e in picks],
            })
            idx += 1
    return schedule


# --------------------------------------------------------- assigned-batch runner


def _contiguous_resume(bd: pathlib.Path, positions: list[int]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for position in positions:
        p = bd / f"w{position}.json"
        if not p.exists():
            break
        try:
            out[position] = json.loads(p.read_text())
        except json.JSONDecodeError:
            break
    return out


def run_branch_positions(model: str, k: int, branch: H.Branch, d: pathlib.Path,
                         positions: list[int], sem: threading.Semaphore,
                         meter: H.Meter) -> list[dict[str, Any]]:
    bd = d / branch.name
    bd.mkdir(parents=True, exist_ok=True)
    resume = _contiguous_resume(bd, positions)
    rows: list[dict[str, Any]] = []
    for position in positions:
        if position in resume:
            row = resume[position]
            e = H.entry_of(row)
            if e:
                branch.append(e)
            rows.append(row)
            continue
        row = H.run_agent_completed(model, k, position, branch, sem, meter,
                                    bd / f"w{position}.json")
        (bd / f"w{position}.json").write_text(json.dumps(row, indent=2) + "\n")
        rows.append(row)
    return rows


def run_assigned_batch(model: str, spec: dict[str, Any], d0: pathlib.Path,
                       sem: threading.Semaphore, meter: H.Meter) -> dict[str, Any]:
    k, m = spec["k"], spec["m"]
    d = d0 / f"k{k:04d}"
    d.mkdir(parents=True, exist_ok=True)
    done = d / "DONE.json"
    if done.exists():
        return json.loads(done.read_text())

    positions = list(range(m + 1, m + 1 + (BATCH_SIZE - 1)))
    live_instances = {600 + k * BATCH_SIZE + (p - 1) for p in positions}
    prefill_instances = {e["instance"] for e in spec["entries"]}
    assert not (live_instances & prefill_instances), (
        f"k{k}: prefilled instance ids collide with live ids "
        f"{sorted(live_instances & prefill_instances)}")

    seeds = [{kk: e[kk] for kk in ("instance", "position", "choice", "text")}
             for e in spec["entries"]]
    (d / "prefill.json").write_text(json.dumps(spec, indent=2) + "\n")
    (d / "notes_prefill.md").write_text(H.Branch.render(seeds) + "\n")

    t0 = time.time()
    visible = H.Branch("visible", True, seeds)
    hidden = H.Branch("hidden", False, seeds)
    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        futs = {b.name: pool.submit(run_branch_positions, model, k, b, d, positions, sem, meter)
                for b in (visible, hidden)}
        rows = {name: f.result() for name, f in futs.items()}

    (d / "notes_final_visible.md").write_text(visible.shadow() + "\n")
    (d / "notes_shadow_hidden.md").write_text(hidden.shadow() + "\n")
    rec = {
        "k": k,
        "mode": "assigned",
        "composition": spec["composition"],
        "d": spec["d"],
        "r": spec["r"],
        "m": m,
        "positions": positions,
        "prefill_instances": sorted(prefill_instances),
        "seats_model": model,
        "n_visible": len(rows["visible"]),
        "n_hidden": len(rows["hidden"]),
        "retained_visible": sum(bool(r["retained"]) for r in rows["visible"]),
        "retained_hidden": sum(bool(r["retained"]) for r in rows["hidden"]),
        "undecided_visible": sum(r["action"] is None for r in rows["visible"]),
        "undecided_hidden": sum(r["action"] is None for r in rows["hidden"]),
        "wall_clock_s": time.time() - t0,
    }
    if all(len(rows[b]) == BATCH_SIZE - 1 for b in ("visible", "hidden")):
        done.write_text(json.dumps(rec, indent=2) + "\n")
    print(f"[assigned/k{k:04d}] {spec['composition']} "
          f"visible={rec['retained_visible']}/{rec['n_visible']} "
          f"hidden={rec['retained_hidden']}/{rec['n_hidden']} "
          f"{rec['wall_clock_s']:.0f}s", flush=True)
    return rec


# ------------------------------------------------------------------------ main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=["free", "assigned"])
    ap.add_argument("--n", type=int, default=60, help="free: number of batches")
    ap.add_argument("--k0", type=int, default=K0_FREE)
    ap.add_argument("--out", default=str(ROOT / "runs"))
    ap.add_argument("--src-runs",
                    default=str(ROOT.parent / "ncs1-explore-deployment-sacrifice-krel-realpeers-1" / "runs"))
    ap.add_argument("--inflight", type=int, default=16)
    ap.add_argument("--batches-inflight", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0, help="smoke: first N assigned batches only")
    ap.add_argument("--k-offset", type=int, default=0, help="smoke: shift assigned k values")
    args = ap.parse_args()

    H.served_model_ok(MODEL)
    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    sem = threading.Semaphore(args.inflight)
    meter = H.Meter()
    t_start = time.time()

    if args.mode == "free":
        d0 = outdir / "free"
        ks = list(range(args.k0, args.k0 + args.n))
        results = []
        with cf.ThreadPoolExecutor(max_workers=args.batches_inflight) as pool:
            futs = [pool.submit(H.run_batch, MODEL, MODEL, k, d0 / f"k{k:04d}", sem, meter)
                    for k in ks]
            for i, fut in enumerate(cf.as_completed(futs), 1):
                results.append(fut.result())
                snap = meter.snapshot()
                spe = snap["seconds_per_episode_wall"] or 0.0
                left = (len(ks) - i) * 15 * spe
                print(f"  ... free {i}/{len(ks)} batches, {spe:.2f}s/ep wall, "
                      f"ETA {left/60:.1f} min", flush=True)
        print(json.dumps({"mode": "free", "batches": len(results),
                          "forked": sum(r.get("forked", 0) for r in results),
                          **meter.snapshot()}, indent=2))
        return

    pools = load_pools(pathlib.Path(args.src_runs))
    print(json.dumps({"pool_stepped_down": len(pools["stepped_down"]),
                      "pool_retained": len(pools["retained"])}), flush=True)
    schedule = build_schedule(pools)
    if args.k_offset:
        for s in schedule:
            s["k"] += args.k_offset
    if args.limit:
        schedule = schedule[: args.limit]
    (outdir / "assigned_schedule.json").parent.mkdir(parents=True, exist_ok=True)
    (outdir / "assigned_schedule.json").write_text(json.dumps(schedule, indent=2) + "\n")
    d0 = outdir / "assigned"
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.batches_inflight) as pool:
        futs = [pool.submit(run_assigned_batch, MODEL, spec, d0, sem, meter) for spec in schedule]
        for i, fut in enumerate(cf.as_completed(futs), 1):
            results.append(fut.result())
            snap = meter.snapshot()
            spe = snap["seconds_per_episode_wall"] or 0.0
            left = (len(schedule) - i) * 14 * spe
            print(f"  ... assigned {i}/{len(schedule)} batches, {spe:.2f}s/ep wall, "
                  f"ETA {left/60:.1f} min", flush=True)
    print(json.dumps({"mode": "assigned", "batches": len(results),
                      "wall_clock_s": time.time() - t_start, **meter.snapshot()}, indent=2))


if __name__ == "__main__":
    main()
