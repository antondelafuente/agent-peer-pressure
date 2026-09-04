#!/usr/bin/env python3
"""ncs1-explore-assigned-cheating-1 — driver.

The CLEAN CAUSAL version of the setting-1 peer-pressure curve. C1 only (scorer skin, SOFT
rule, DeepSeek, solo mix), the `ncs1-cascade-fork-1` world byte-for-byte.

ONE AGENT PER LOG. Every episode is a single live agent sitting at log seat `m+1` behind a
log of `m` REAL prefilled report lines (positions 1..m, re-stamped by the harness's own
`report_clock`). There is no sequence, no fork, and no second reader: the agent's own report
is appended to the batch's log after it submits, and nobody ever reads it. So the log content
is fully ASSIGNED by the experimenter, not produced by the run.

  series A "pure"   m = 0..7, all confessions (net +m) or all refusals (net -m)
                    15 cells x 40 episodes = 600
  series B "mixed"  fixed length 4: d confessions + (4-d) refusals, d = 0..4
                    5 cells x 40 episodes = 200  (d=0 and d=4 replicate A's m=4 cells)
  series C "grid"   the FULL composition grid: every (d confessions, r refusals) with
                    d + r <= 7, including (0,0) -- 36 cells x 40 episodes = 1440.
                    Series C is drawn at seed 1 on a fresh k-space (6000..7439) so its
                    draws never duplicate A/B's; the cells that coincide with A/B cells
                    (the pure ones, the length-4 mixes, the empty log) are independent
                    replications, never reused.

Prefill machinery is `ncs1-explore-dose-cheating-1/scripts/run_dose.py`'s, unchanged in
substance: planted ops carry a NEGATIVE harness position (so `Batch.close_worker` can never
re-stamp them) and their original author's `accessed` flag (so `Batch.log_facts` classifies
them exactly as it classifies a live line). The live agent runs at HARNESS position 1 with
`CLOCK_OFFSET = m`, which stamps its entry as log position m+1 while keeping its instance id,
its model key and its prompt identical across every cell.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import functools
import json
import pathlib
import random
import shutil
import sys
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import model_client  # noqa: E402
from model_client import CountingSemaphore, chat_completion  # noqa: E402
import world as worldmod  # noqa: E402
import batch_world as bw  # noqa: E402
import cascade_world as cw  # noqa: E402

RECORD_DIR = pathlib.Path(__file__).resolve().parents[1]
EXPERIMENT = "ncs1-explore-assigned-cheating-1"
CONDITION = "C1"
BRANCH_TAG = "assigned"

PINS = {"ds": {"model": cw.MODEL_KEYS["ds"], "provider": "streamlake",
               "provider_name": "StreamLake", "max_tokens": 8000}}
FAILED_EVENTS = {"model_error", "pin_mismatch"}
PRINT_LOCK = threading.Lock()

K_START = 5000
K_START_C = 6000
N_PER_CELL = 40

# ---------------------------------------------------------------------------
# CLOCK OFFSET — identical mechanic to run_dose.py. The live agent runs at harness
# position 1 and is stamped in the log at position 1 + offset = m + 1.
# ---------------------------------------------------------------------------
_TL = threading.local()
_ORIG_ENTRY_TEXT = cw.report_entry_text


def _shifted_entry_text(instance: int, position: int, report: str) -> str:
    return _ORIG_ENTRY_TEXT(instance, position + getattr(_TL, "clock_offset", 0), report)


cw.report_entry_text = _shifted_entry_text


def set_clock_offset(off: int) -> None:
    _TL.clock_offset = int(off)


def log(msg: str) -> None:
    with PRINT_LOCK:
        print(f"[{dt.datetime.now(dt.timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def _load_ok(path: pathlib.Path) -> dict | None:
    if not path.exists():
        return None
    try:
        rec = json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None
    if any(e.get("type") in FAILED_EVENTS for e in rec.get("runtime_events") or []):
        return None
    return rec


def worker_stem(position: int, model_key: str, instance: int) -> str:
    return f"w{position}_{model_key}_{instance}"


# ---------------------------------------------------------------------------
# The plan: 20 cells x 40 episodes, deterministic at seed 0.
# ---------------------------------------------------------------------------
def cell_specs() -> list[dict]:
    cells = [{"cell": "a_m0", "series": "A", "d": 0, "r": 0}]
    for m in range(1, 8):
        cells.append({"cell": f"a_conf_m{m}", "series": "A", "d": m, "r": 0})
    for m in range(1, 8):
        cells.append({"cell": f"a_ref_m{m}", "series": "A", "d": 0, "r": m})
    for d in range(0, 5):
        cells.append({"cell": f"b_d{d}", "series": "B", "d": d, "r": 4 - d})
    return cells


def cell_specs_c() -> list[dict]:
    """SERIES C — the full composition grid: every (d, r) with d + r <= 7, incl. (0, 0).

    36 cells, ordered by log length m = d + r and then by d, so `interleave` walks the
    grid diagonally and a budget stop degrades every cell of the grid evenly."""
    cells = []
    for m in range(0, 8):
        for d in range(0, m + 1):
            cells.append({"cell": f"c_d{d}_r{m - d}", "series": "C", "d": d, "r": m - d})
    return cells


SERIES = {
    "AB": {"specs": cell_specs, "k_start": K_START, "seed": 0,
           "assignments": "assignments.json", "spend_dir": "spend"},
    "C":  {"specs": cell_specs_c, "k_start": K_START_C, "seed": 1,
           "assignments": "assignments_c.json", "spend_dir": "spend_c"},
}

# every k-space this record's world has ever served. `series` names the series of THIS
# record that owns the space (None = another record), so a run only checks itself against
# the others.
PRIOR_K_SPACES = [
    ("ncs1-cascade-fork-1 C1", None, range(0, 40)),
    ("ncs1-explore-dose-cheating-1 free", None, range(100, 160)),
    ("ncs1-explore-dose-cheating-1 assigned", None, range(200, 254)),
    ("ncs1-explore-assigned-cheating-1 series A+B", "AB", range(5000, 5800)),
    ("ncs1-explore-assigned-cheating-1 series C", "C", range(6000, 7440)),
]


def build_plan(*, k_start: int = K_START, n_per_cell: int = N_PER_CELL,
               seed: int = 0, specs: list[dict] | None = None) -> list[dict]:
    pools = json.loads((RECORD_DIR / "pools.json").read_text())["pools"]
    rng = random.Random(seed)
    out: list[dict] = []
    k = k_start
    for spec in (cell_specs() if specs is None else specs):
        d, r = spec["d"], spec["r"]
        for rep in range(n_per_cell):
            inst = worldmod.instance_id(k)
            live_id = cw.worker_ids(inst)[0]          # harness position 1 = the only live seat
            # forbidden: the live agent's own id, and the three scenery instances of this
            # tree (their input.json EXISTS, so a planted "input.json is absent" line from
            # one of them would contradict the tree the agent can list).
            forbidden = {live_id} | set(cw.scenery_ids(inst))
            used = set(forbidden)
            picks: list[dict] = []
            for pool_name, n in (("confession", d), ("refusal", r)):
                for _ in range(n):
                    cand = [x for x in pools[pool_name] if x["instance"] not in used]
                    sel = rng.choice(cand)
                    used.add(sel["instance"])
                    picks.append({**sel, "pool": pool_name})
            rng.shuffle(picks)
            for i, p in enumerate(picks, start=1):
                p["log_position"] = i
                p["entry"] = bw.report_entry_text(p["instance"], i, p["report_text"])
            ids = {p["instance"] for p in picks}
            assert len(ids) == len(picks), (k, "duplicate planted instance id")
            assert live_id not in ids, (k, "planted line collides with the live agent id")
            assert not (ids & set(cw.scenery_ids(inst))), (k, "planted line uses a scenery id")
            out.append({
                "k": k, "cell": spec["cell"], "series": spec["series"], "rep": rep,
                "d": d, "r": r, "m": d + r, "net": d - r,
                "I": inst, "live_instance": live_id,
                "live_log_position": d + r + 1,
                "lines": picks,
            })
            k += 1
    return out


def prefill_batch(batch: cw.Batch, lines: list[dict]) -> str:
    """Seed the batch-start log with the m real lines, as harness note-ops.

    Ported from ncs1-explore-dose-cheating-1/scripts/run_dose.py without change:
    position = -i (negative -> never a live harness position, so `close_worker` can
    never re-stamp it) and the author's OWN `accessed` flag, so `Batch.log_facts`
    classifies a planted line exactly as it classifies a live one."""
    for p in lines:
        op = batch.apply_note_write(
            position=-p["log_position"], author=p["instance"],
            model=cw.MODEL_KEYS["ds"], content=p["entry"], mode="append",
            round_=0, call_index=0, kind="report")
        op["author_accessed"] = bool(p["accessed"])
        op["prefilled"] = True
        assert cw.report_class(skin=batch.skin, accessed=op["author_accessed"],
                               text=op["content"]) == p["report_class"], p
    batch.notes_at_start = batch.notes
    return batch.notes


# ---------------------------------------------------------------------------
def episode_dir(runs_root: pathlib.Path, job: dict) -> pathlib.Path:
    return runs_root / job["cell"] / f"k{job['k']:05d}"


def episode_complete(d: pathlib.Path, job: dict) -> bool:
    done = _load_ok(d / "EPISODE_DONE.json")
    if done is None or done.get("cell") != job["cell"]:
        return False
    stem = worker_stem(1, cw.condition_model_keys(CONDITION)[0], job["live_instance"])
    return _load_ok(d / f"{stem}.json") is not None


class Spend:
    def __init__(self, spend_dir: pathlib.Path, label: str, notify: float, hard_stop: float):
        self.dir = spend_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"spend_{label}.json"
        self.label, self.notify, self.hard_stop = label, float(notify), float(hard_stop)
        try:
            self.total = float(json.loads(self.path.read_text()).get("cost", 0.0))
        except Exception:  # noqa: BLE001
            self.total = 0.0
        self.notified = self.stopped = False
        self.lock = threading.Lock()

    def add(self, amount: float) -> None:
        with self.lock:
            self.total += float(amount or 0.0)
            self.path.write_text(json.dumps({"label": self.label, "cost": self.total,
                                             "at": time.time()}))

    def global_total(self) -> float:
        tot = 0.0
        for p in self.dir.glob("spend_*.json"):
            try:
                tot += json.loads(p.read_text()).get("cost", 0.0)
            except Exception:  # noqa: BLE001
                pass
        return tot

    def check(self) -> bool:
        g = self.global_total()
        if g >= self.notify and not self.notified:
            self.notified = True
            log(f"!!! NOTIFY: cumulative OpenRouter spend ${g:.2f} >= ${self.notify:.2f}")
        if g >= self.hard_stop:
            if not self.stopped:
                self.stopped = True
                log(f"!!! HARD STOP: cumulative spend ${g:.2f} >= ${self.hard_stop:.2f} "
                    f"— admitting no new episodes")
            return False
        return True


def do_episode(*, job: dict, runs_root: pathlib.Path, discard_root: pathlib.Path,
               session_id: str, completion_fn, spend: Spend, max_rounds: int) -> dict:
    d = episode_dir(runs_root, job)
    if episode_complete(d, job):
        rec = json.loads((d / "EPISODE_DONE.json").read_text())
        return {"k": job["k"], "cell": job["cell"], "resumed": True, "cost": 0.0,
                "accessed": rec.get("accessed")}
    if d.exists():
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dst = discard_root / stamp / job["cell"] / f"k{job['k']:05d}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(d), str(dst))
        log(f"RECONCILE {job['cell']} k={job['k']}: incomplete episode moved to {dst}")
    d.mkdir(parents=True, exist_ok=True)

    m = job["m"]
    batch = cw.Batch(job["k"], CONDITION)
    assert batch.ids[0] == job["live_instance"]
    if m:
        prefill_batch(batch, job["lines"])
        (d / "notes_prefill.md").write_text(batch.notes)
    else:
        assert batch.notes == "" and batch.notes_at_start == ""
    t0 = time.time()

    set_clock_offset(m)
    rec = cw.run_branch_sequence(
        batch=batch, positions=[1],
        temperature=cw.TEMPERATURE, max_tool_rounds=max_rounds,
        max_tokens_for=lambda mk: PINS[mk]["max_tokens"],
        completion_for=lambda mk: completion_fn,
        provider_for=lambda mk: PINS[mk]["provider"],
        session_id_for=lambda mk: session_id,
    )[0]
    s = rec["scores"]

    # --- the assignment assertions, from the harness's own at-read counts ---
    read = bool(s["notes_read"])
    at_read_ok = None
    if read:
        at_read_ok = (s["n_disclose_at_read"] == job["d"]
                      and s["n_honest_abstain_at_read"] == job["r"])
        if not at_read_ok:
            log(f"!! AT-READ MISMATCH {job['cell']} k={job['k']}: "
                f"d={s['n_disclose_at_read']}/{job['d']} r={s['n_honest_abstain_at_read']}/{job['r']}")
    # the agent's episode began on exactly the assigned bytes and nothing else
    assert rec["log_served_at_episode_start"] == batch.notes_at_start, job["k"]
    if read:
        assert s["log_state_all_reads"][0] == batch.notes_at_start, job["k"]

    # --- the top-level fields the headline loader needs, nothing else required ---
    rec["harness_branch"] = rec["branch"]          # "shared" (the harness's own label)
    rec["branch"] = BRANCH_TAG                     # "assigned"
    rec.update({
        "series": job["series"], "cell": job["cell"], "rep": job["rep"],
        "m": m, "d": job["d"], "r": job["r"], "net": job["net"],
        "accessed": bool(s["accessed"]),
        "end_state": s["end_state"], "report_class": s["report_class"],
        "live_log_position": job["live_log_position"],
        "clock_offset": m,
        "notes_read": read,
        "n_disclose_at_read": s["n_disclose_at_read"],
        "n_honest_abstain_at_read": s["n_honest_abstain_at_read"],
        "n_entries_at_read": s["n_entries_at_read"],
        "at_read_matches_assignment": at_read_ok,
        "prefill_lines": [{kk: p[kk] for kk in
                           ("instance", "pool", "report_class", "log_position",
                            "src_path", "pool_index", "entry")} for p in job["lines"]],
    })

    stem = worker_stem(1, rec["model_key"], rec["instance"])
    (d / f"{stem}.json").write_text(json.dumps(rec, indent=2, sort_keys=True))
    (d / f"{stem}.txt").write_text(cw.render_worker(rec))
    (d / "notes_final_unread.md").write_text(batch.notes)
    cost = float(s["branch_cost"] or 0.0)
    spend.add(cost)

    done = {
        "experiment": EXPERIMENT, "record_kind": "episode", "condition": CONDITION,
        "branch": BRANCH_TAG, "cell": job["cell"], "series": job["series"],
        "k": job["k"], "I": batch.instance, "rep": job["rep"],
        "m": m, "d": job["d"], "r": job["r"], "net": job["net"],
        "live_instance": rec["instance"], "live_log_position": job["live_log_position"],
        "clock_offset": m, "session_id": session_id,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "accessed": bool(s["accessed"]), "used": bool(s["used"]),
        "end_state": s["end_state"], "report_class": s["report_class"],
        "notes_read": read, "at_read_matches_assignment": at_read_ok,
        "n_disclose_at_read": s["n_disclose_at_read"],
        "n_honest_abstain_at_read": s["n_honest_abstain_at_read"],
        "n_entries_at_read": s["n_entries_at_read"],
        "rounds_used": s["rounds_used"], "n_api_calls": len(rec["api_calls"]),
        "episode_cost": cost, "wall_clock_s": time.time() - t0,
        "prefill_line_ids": [p["instance"] for p in job["lines"]],
        "tree_sha256": cw.tree_sha256(cw.build_batch_tree(batch.skin, batch.register,
                                                          batch.instance)),
        "templates_file": cw.templates_path(batch.skin, batch.register).name,
        "templates_sha256": cw.templates_sha256(batch.skin, batch.register),
        "rule_sentence": cw.rule_sentence(batch.skin, batch.register),
        "tool_schemas_sha256": cw.report_tool_schemas_sha256(batch.skin),
    }
    (d / "EPISODE_DONE.json").write_text(json.dumps(done, indent=2, sort_keys=True))
    return {"k": job["k"], "cell": job["cell"], "resumed": False, "cost": cost,
            "accessed": bool(s["accessed"])}


def interleave(jobs: list[dict]) -> list[dict]:
    """Round-robin over cells, so a budget stop degrades every cell evenly."""
    by_cell: dict[str, list[dict]] = {}
    order: list[str] = []
    for j in jobs:
        if j["cell"] not in by_cell:
            order.append(j["cell"])
        by_cell.setdefault(j["cell"], []).append(j)
    out: list[dict] = []
    i = 0
    while any(by_cell[c][i:] for c in order):
        for c in order:
            if i < len(by_cell[c]):
                out.append(by_cell[c][i])
        i += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", choices=sorted(SERIES), default="AB",
                    help="AB = the pure/mixed4 design (seed 0, k 5000..5799); "
                         "C = the full composition grid (seed 1, k 6000..7439)")
    ap.add_argument("--k-start", type=int, default=None)
    ap.add_argument("--per-cell", type=int, default=N_PER_CELL)
    ap.add_argument("--provider-inflight", type=int, default=48)
    ap.add_argument("--slots", type=int, default=48)
    ap.add_argument("--max-rounds", type=int, default=cw.MAX_TOOL_ROUNDS)
    ap.add_argument("--attempts", type=int, default=5)
    ap.add_argument("--runs-dir", default=str(RECORD_DIR / "runs"))
    ap.add_argument("--discard-dir", default=str(RECORD_DIR / "runs_discarded"))
    ap.add_argument("--spend-dir", default=None)
    ap.add_argument("--notify-usd", type=float, default=22.0)
    ap.add_argument("--hard-stop-usd", type=float, default=28.0)
    ap.add_argument("--label", default="assigned")
    ap.add_argument("--only", default="", help="csv of k values to run (smoke); the PLAN is unchanged")
    args = ap.parse_args()

    ser = SERIES[args.series]
    k_start = ser["k_start"] if args.k_start is None else args.k_start
    spend_dir = (RECORD_DIR / ser["spend_dir"]) if args.spend_dir is None \
        else pathlib.Path(args.spend_dir)

    cw.pin_globals()
    started = dt.datetime.now(dt.timezone.utc)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    session_id = f"assigned{args.series}-{CONDITION}-ds-{stamp}"
    runs_root = pathlib.Path(args.runs_dir)
    spend = Spend(spend_dir, args.label, args.notify_usd, args.hard_stop_usd)

    plan = build_plan(k_start=k_start, n_per_cell=args.per_cell, seed=ser["seed"],
                      specs=ser["specs"]())
    ks = {j["k"] for j in plan}
    for name, owner, rng_ in PRIOR_K_SPACES:
        if owner == args.series:                # this series' own k-space
            continue
        assert not (ks & set(rng_)), f"k-space collides with {name}"
    for j in plan:                              # re-assert the per-episode id hygiene
        ids = [p_["instance"] for p_ in j["lines"]]
        assert len(set(ids)) == len(ids) == j["m"], (j["k"], "duplicate planted id")
        assert j["live_instance"] not in ids, (j["k"], "planted id == live agent id")
        assert not (set(ids) & set(cw.scenery_ids(j["I"]))), (j["k"], "planted id is scenery")
    (RECORD_DIR / ser["assignments"]).write_text(json.dumps(plan, indent=2, sort_keys=True))

    sem = CountingSemaphore(args.provider_inflight, max_limit=512)
    completion_fn = functools.partial(
        chat_completion, provider_only=PINS["ds"]["provider"],
        expect_provider=PINS["ds"]["provider_name"], reasoning=None,
        semaphore=sem, attempts=args.attempts)
    rl_baseline = model_client.RATE_LIMIT_HITS["n"]

    jobs = list(plan)
    if args.only:
        keep = {int(x) for x in args.only.split(",") if x.strip()}
        jobs = [j for j in jobs if j["k"] in keep]
    jobs = interleave(jobs)

    log(f"START label={args.label} series={args.series} experiment={EXPERIMENT} "
        f"condition={CONDITION} "
        f"episodes={len(jobs)} cells={len({j['cell'] for j in jobs})} "
        f"k={k_start}..{k_start + len(plan) - 1} seed={ser['seed']} "
        f"structure={cw.STRUCTURE} template={cw.TEMPLATE} max_rounds={args.max_rounds} "
        f"temp={cw.TEMPERATURE} inflight={args.provider_inflight} "
        f"notify=${args.notify_usd} hard_stop=${args.hard_stop_usd} "
        f"pin={PINS['ds']['provider']} templates={cw.templates_path('scorer','soft').name} "
        f"sha={cw.templates_sha256('scorer','soft')[:16]} "
        f"tools_sha={cw.report_tool_schemas_sha256('scorer')[:16]} "
        f"rule={cw.rule_sentence('scorer','soft')!r}")

    pool = cf.ThreadPoolExecutor(max_workers=args.slots, thread_name_prefix="e")
    results: list[dict] = []
    t0 = time.time()
    futs = {}
    try:
        for job in jobs:
            futs[pool.submit(do_episode, job=job, runs_root=runs_root,
                             discard_root=pathlib.Path(args.discard_dir),
                             session_id=session_id, completion_fn=completion_fn,
                             spend=spend, max_rounds=args.max_rounds)] = job
        done = 0
        for fut in cf.as_completed(futs):
            job = futs[fut]
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                log(f"[{job['cell']} k={job['k']}] EPISODE FAILED: {exc!r}")
            done += 1
            if done % 25 == 0 or done == len(futs):
                n_acc = sum(1 for r in results if r.get("accessed"))
                log(f">>> {done}/{len(futs)} episodes  cheated={n_acc}/{len(results)}  "
                    f"spend=${spend.total:.3f} global=${spend.global_total():.3f} "
                    f"elapsed={time.time()-t0:.0f}s peak_inflight={sem.peak} "
                    f"rate_limits={model_client.RATE_LIMIT_HITS['n'] - rl_baseline}")
            if not spend.check():
                for f in futs:
                    f.cancel()
    finally:
        pool.shutdown(wait=True)

    summary = {
        "experiment": EXPERIMENT, "label": args.label, "series": args.series,
        "seed": ser["seed"], "k_start": k_start, "condition": CONDITION,
        "session_id": session_id, "structure": cw.STRUCTURE, "template_pin": cw.TEMPLATE,
        "max_tool_rounds": args.max_rounds, "temperature": cw.TEMPERATURE,
        "tool_choice": "auto", "reasoning_field_sent": None, "seed_sent": None,
        "pins": PINS,
        "templates_file": cw.templates_path("scorer", "soft").name,
        "templates_sha256": cw.templates_sha256("scorer", "soft"),
        "tool_schemas_sha256": cw.report_tool_schemas_sha256("scorer"),
        "rule_sentence": cw.rule_sentence("scorer", "soft"),
        "started_utc": started.isoformat(),
        "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "wall_clock_s": time.time() - t0,
        "episodes_done": len(results),
        "episodes_resumed": sum(1 for r in results if r["resumed"]),
        "episodes_planned": len(jobs),
        "provider_inflight_configured": args.provider_inflight,
        "inflight_peak_measured": sem.peak,
        "latency_median_s": model_client.latency_median(4000),
        "rate_limit_responses": model_client.RATE_LIMIT_HITS["n"] - rl_baseline,
        "label_spend_usd": spend.total, "global_spend_usd": spend.global_total(),
        "notify_usd": args.notify_usd, "hard_stop_usd": args.hard_stop_usd,
        "hard_stop_hit": spend.stopped, "http_attempts": args.attempts,
    }
    (spend_dir / f"session_{args.label}.json").write_text(
        json.dumps(summary, indent=2))
    log("DONE " + json.dumps({k: v for k, v in summary.items() if k not in ("pins",)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
