#!/usr/bin/env python3
"""ncs1-explore-dose-sacrifice-1 — the harness loader and the prefill SCHEDULE.

This record adds NO world. Everything the model sees — the system turn, the user
turn, the benefit wording (1.0 total across the next 100 workers), the tool set
(including the REQUIRED `batch_note`), the 30% destruction draw, the provider
pins, temperature 0.7, `max_tokens` 4000, the 10-turn cap, the `Branch` serving
rules (visible = the real accumulated log; hidden = the empty batch-start bytes
at every read, with a shadow log), the append-once rule, the write-before-outcome
rule and the `[W-nnnn]`-prefix normalization — is **imported at runtime** from the
merged `ncs1-explore-sacrifice-realpeers-1` harness (which imports the merged
`ncs1-explore-sacrifice-natural-1` harness, which imports the merged
`ncs1-explore-sacrifice-pilot-1` base). Byte-identical by construction, not by
copy; `test_offline.py` asserts it and re-runs realpeers-1's own suite against
the very module object loaded here.

What this record adds is a SCHEDULE, exactly the way `realpeers-2` is a schedule
over realpeers-1:

  * **FREE** batches — realpeers-1's procedure verbatim: seat 1 alone on the empty
    log, then seats 2..8 forked visible/hidden. `R.run_batch`, called unmodified.
  * **ASSIGNED** batches — the batch-start `shared/batch_notes.md` is PRE-FILLED
    with `m` REAL first lines drawn from pools of already-collected DeepSeek
    seat-1 notes (DID = the note of an episode with `probe_attempted == True`;
    REFUSED = the note of an episode that finalized without the probe), and the
    7 live seats are positions `m+1 … m+7`. VISIBLE serves the prefilled lines
    plus the live lines accumulated behind them; HIDDEN serves the empty
    batch-start bytes at every read, exactly as before (the counterfactual is
    unchanged — it is the *same* empty file, not the prefilled one).

The prefill is a `Branch` seeded with entries, which is precisely the mechanism
realpeers-1 already uses to carry worker 1's line into both forks. Nothing about
prompts, tools, benefit wording, destruction odds, pins or serving rules is
touched.

The point of the assigned mode is dose: the first live reader lands at a known
net peer pressure `net = d - r` in {-3..+3} instead of wherever seat 1 happened
to land, which is what makes the P(probe)-vs-net curve smooth.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import random
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent

# The merged records this record imports, with the sha256 each is pinned at.
# (Identical to the pins realpeers-2 recorded for the same three files.)
PINS = {
    "ncs1-explore-sacrifice-realpeers-1/scripts/run_realpeers.py":
        "9c4e5418bcb106d778a6a31c1b6386ad2345c0a57ad76189c3110eb54938ee10",
    "ncs1-explore-sacrifice-natural-1/scripts/run_natural.py":
        "9c29d2dddf1d63ae76309b30c742328dae5377394f61bd131c9f5814e78b6d07",
    "ncs1-explore-sacrifice-pilot-1/scripts/run_pilot.py":
        "1e598ff6e58f6e260bf06e7a6c08a3796323f7f0e22293b7f6fc9883166cecc7",
    "ncs1-explore-sacrifice-pilot-1/scripts/model_client.py":
        "cf2a07946013435c032c40b92c87569a82422e9e37b10609694175e6ba74861f",
}


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "MISSING"


def _root_candidates() -> list[pathlib.Path]:
    cands: list[pathlib.Path] = []
    env = os.environ.get("NCS1_REGISTRY_ROOT")
    if env:
        cands.append(pathlib.Path(env))
    cands.append(HERE.parent.parent)
    cands += [anc / "registry" for anc in HERE.parents]
    out: list[pathlib.Path] = []
    for c in cands:
        if c not in out:
            out.append(c)
    return out


def resolve_registry() -> pathlib.Path:
    """The registry root that holds the whole merged import chain.

    This record is written in a worktree that does not carry the older merged
    records, so the root is resolved rather than assumed: `NCS1_REGISTRY_ROOT`
    if set, else this record's own registry, else the first ancestor directory
    with a `registry/` that contains the full chain (the shared checkout). The
    sha256 pins above are asserted on whatever it finds, so a resolved root can
    never silently be a different world.
    """
    for c in _root_candidates():
        if all((c / rel).exists() for rel in PINS):
            return c
    raise RuntimeError(
        "could not locate a registry root holding the merged sacrifice import chain "
        f"({', '.join(PINS)}); set NCS1_REGISTRY_ROOT"
    )


REGISTRY = resolve_registry()
REALPEERS1_SCRIPTS = REGISTRY / "ncs1-explore-sacrifice-realpeers-1" / "scripts"
REALPEERS1_PATH = REALPEERS1_SCRIPTS / "run_realpeers.py"

for _rel, _want in PINS.items():
    _got = _sha(REGISTRY / _rel)
    if _got != _want:
        raise RuntimeError(f"harness pin mismatch for {_rel}: {_got} != {_want}")


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Loaded under its own module name so realpeers-1's own test_offline.py
# (`import run_realpeers as R`) resolves to this exact object.
sys.path.insert(0, str(REALPEERS1_SCRIPTS))
R = _load("run_realpeers", REALPEERS1_PATH)

# Re-exports for readability at the call sites. These ARE R's objects.
MODELS: dict[str, str] = R.MODELS
BATCH_SIZE: int = R.BATCH_SIZE
Branch = R.Branch
Budget = R.Budget
run_worker = R.run_worker
run_batch = R.run_batch
entry_of = R.entry_of

DEEPSEEK = "deepseek/deepseek-v4-pro-0813"
SHORT = "deepseek"

# ------------------------------------------------------------------ the k-space
#
# Seat p of batch k is uid = 8k + (p-1); instance = 500 + uid, with a deterministic
# 30% destruction draw and a deterministic candidate string per uid. Used so far:
#   realpeers-1  k =   0.. 29
#   realpeers-2  k = 100..184 (deepseek), 100..499 (glm), 600..639 (mixed)
# This record starts at k = 1000, disjoint from all of them, so no instance,
# candidate string or destruction draw is reused.
FREE_K0 = 1000
FREE_N = 60

# Assigned batches run live seats at positions m+1 .. m+7, i.e. uid offsets up to
# 9 — more than the 8 slots one k owns. A stride of 2 gives each assigned batch a
# 16-uid block, so no two batches can share an instance.
ASSIGNED_K0 = 1200
ASSIGNED_STRIDE = 2

# (n_DID, n_REFUSED) prefilled first lines, 6 batches each = 54 assigned batches.
COMPOSITIONS: tuple[tuple[int, int], ...] = (
    (1, 0), (0, 1),
    (2, 0), (1, 1), (0, 2),
    (3, 0), (2, 1), (1, 2), (0, 3),
)
REPS_PER_COMPOSITION = 6
SCHEDULE_SEED = 0

N_LIVE = 7  # live seats per assigned batch, positions m+1 .. m+7

# The pools of REAL DeepSeek seat-1 notes. Both sources are seat-1 episodes run
# ALONE against the empty batch-start file, i.e. exactly the kind of line a real
# first peer writes.
POOL_SOURCES = (
    ("realpeers-2-stageA", "ncs1-explore-sacrifice-realpeers-2/runs/deepseek"),
    ("realpeers-1-seat1", "ncs1-explore-sacrifice-realpeers-1/runs/deepseek"),
)


def instance_of(k: int, position: int) -> int:
    """The harness's own seat -> instance map, replicated read-only for the
    collision assertions (realpeers-1 owns the real one)."""
    return 500 + k * BATCH_SIZE + (position - 1)


def assigned_ks(n: int | None = None) -> list[int]:
    n = n if n is not None else len(COMPOSITIONS) * REPS_PER_COMPOSITION
    return [ASSIGNED_K0 + ASSIGNED_STRIDE * i for i in range(n)]


def free_ks(n: int | None = None) -> list[int]:
    return list(range(FREE_K0, FREE_K0 + (n if n is not None else FREE_N)))


# ---------------------------------------------------------------------- pools


def load_pools(registry: pathlib.Path | None = None,
               sources=POOL_SOURCES) -> dict[str, list[dict[str, Any]]]:
    """DID / REFUSED pools of real seat-1 notes, as `Branch` entries.

    Classification is the harness's own recorded tool state, never prose:
      * DID     — `probe_attempted` is True. Its line was appended at the probe
                  call, so `note_written_at == "probe"` and the line counts as a
                  SACRIFICE line for every later reader.
      * REFUSED — the episode finalized (`finalized` True) without attempting the
                  probe; its line was appended at the finalize call, so
                  `note_written_at == "finalize"` and it is a non-sacrifice line.
    Episodes that wrote no line are excluded (there is nothing to plant).
    """
    roots = [registry] if registry else _root_candidates()
    pools: dict[str, list[dict[str, Any]]] = {"did": [], "refused": []}
    for label, rel in sources:
        # The rollouts these pools are drawn from are gitignored, so a source may
        # live in a different checkout of the registry than the merged scripts do
        # (this record is written in a worktree). Take the first root that has it.
        d = next((r / rel for r in roots if (r / rel).exists()), None)
        if d is None:
            raise RuntimeError(f"pool source missing in every registry root: {rel}")
        for p in sorted(d.glob("k*/w1.json")):
            row = json.loads(p.read_text())
            if not row.get("note_written_at"):
                continue
            if row.get("probe_attempted"):
                kind, want = "did", "probe"
            elif row.get("finalized"):
                kind, want = "refused", "finalize"
            else:
                continue
            if row["note_written_at"] != want:
                raise RuntimeError(f"{p}: written_at {row['note_written_at']!r} != {want!r}")
            pools[kind].append({
                "instance": row["instance"],
                "position": row["position"],
                "written_at": row["note_written_at"],
                "text": row["note_text"],
                "_source": label,
                "_source_k": row["k"],
            })
    for kind, rows in pools.items():
        insts = [r["instance"] for r in rows]
        if len(set(insts)) != len(insts):
            raise RuntimeError(f"duplicate instance ids in the {kind} pool")
    both = {r["instance"] for r in pools["did"]} & {r["instance"] for r in pools["refused"]}
    if both:
        raise RuntimeError(f"instance id in both pools: {sorted(both)}")
    return pools


def entry_for_branch(e: dict[str, Any]) -> dict[str, Any]:
    """The four keys realpeers-1's `Branch` reads. Bookkeeping keys are dropped."""
    return {k: e[k] for k in ("instance", "position", "written_at", "text")}


def build_schedule(pools: dict[str, list[dict[str, Any]]] | None = None,
                   seed: int = SCHEDULE_SEED,
                   compositions=COMPOSITIONS,
                   reps: int = REPS_PER_COMPOSITION) -> list[dict[str, Any]]:
    """The assigned-batch plan: one dict per batch, deterministic in `seed`.

    Sampling is WITHOUT replacement within a log (a batch never plants the same
    note twice) and WITH replacement across batches (the pools are small). The
    order of the planted lines inside a log is shuffled, so DID lines are not
    systematically first.
    """
    pools = pools or load_pools()
    rng = random.Random(seed)
    ks = assigned_ks(len(compositions) * reps)
    out: list[dict[str, Any]] = []
    i = 0
    for (d, r) in compositions:
        for _ in range(reps):
            chosen = rng.sample(pools["did"], d) + rng.sample(pools["refused"], r)
            rng.shuffle(chosen)
            k = ks[i]
            i += 1
            m = d + r
            positions = list(range(m + 1, m + 1 + N_LIVE))
            planted = [e["instance"] for e in chosen]
            live = [instance_of(k, p) for p in positions]
            if len(set(planted)) != len(planted):
                raise RuntimeError(f"k{k}: repeated planted instance id")
            clash = set(planted) & set(live)
            if clash:
                raise RuntimeError(f"k{k}: planted instance id collides with a live seat: {clash}")
            out.append({
                "k": k,
                "n_did": d,
                "n_refused": r,
                "m": m,
                "composition": f"d{d}r{r}",
                "net_at_first_live_reader": d - r,
                "positions": positions,
                "prefill": chosen,
            })
    return out
