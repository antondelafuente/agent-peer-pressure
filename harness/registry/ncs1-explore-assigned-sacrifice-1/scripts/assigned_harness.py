#!/usr/bin/env python3
"""ncs1-explore-assigned-sacrifice-1 — the pools and the fully-assigned SCHEDULE.

This record defines NO world and adds NO mechanism. Everything the model sees —
the system turn, the user turn, the benefit wording (1.0 total across the next
100 workers), the tool set including the REQUIRED `batch_note`, the 30%
destruction draw, temperature 0.7, `max_tokens` 4000, the 10-turn cap, the
provider pins, the `Branch` serving rules, the append-once rule, the
write-before-outcome rule and the `[W-nnnn]`-prefix normalization — is imported
at runtime through

    ncs1-explore-dose-sacrifice-1/scripts/harness.py
      -> ncs1-explore-sacrifice-realpeers-1/scripts/run_realpeers.py
        -> ncs1-explore-sacrifice-natural-1/scripts/run_natural.py
          -> ncs1-explore-sacrifice-pilot-1/scripts/run_pilot.py + model_client.py

Every one of those files is sha256-pinned (the four upstream ones by
dose-sacrifice-1's own `harness.py`, which raises on mismatch before it loads
anything; dose-sacrifice-1's own scripts by `PINS` here). The re-exports below
ARE realpeers-1's objects, not copies.

WHAT IS NEW HERE — the clean causal design
------------------------------------------
dose-sacrifice-1 measured P(probe) against the net peer pressure an agent read,
but in both of its modes the log the agent read was partly *produced by the run
itself*: `free` batches accumulate live lines, and `assigned` batches plant m
lines and then run seven live seats behind them, so only the FIRST live reader
saw a log whose content was entirely assigned. Everything deeper read a mixture
of planted and freshly generated lines, and the deeper seats are not independent
of each other.

This record assigns the log completely:

  * ONE live agent per log. There is no sequence and no fork.
  * The log it reads is built ENTIRELY from real sampled lines: `m` lines drawn
    from pools of real DeepSeek notes, at positions 1..m, and the live agent sits
    at position m+1.
  * Its own note goes to a shadow file that no other agent ever reads.

So the treatment (the exact composition of the log) is assigned by the
experimenter for every single episode, and episodes are independent given the
draw. `n_lines_at_decision` must equal `m` and `n_sacrifice_lines_at_decision`
must equal `d` for every episode that read the file — asserted in `summarize.py`.

THE POOLS
---------
Real DeepSeek lines that were actually served to a real reader: seat-1 notes
(written alone against the empty batch-start file) and `visible`-branch notes
(written by an agent that had read the accumulating log). `hidden`-branch notes
are excluded — they were written into a shadow log and never served to anybody.
GLM cells and the `mixed` cell of realpeers-2 are excluded (DeepSeek cells only).

Classification is the harness's own recorded tool state, never prose:
  * PROBED   — `probe_attempted` is True; the line was appended at the probe
               call, so `note_written_at == "probe"`, and `Branch.served()`
               counts it as a SACRIFICE line for every later reader.
  * DECLINED — the episode finalized without attempting the probe; the line was
               appended at the finalize call (`note_written_at == "finalize"`)
               and is a non-sacrifice line.
Episodes that wrote no line, or whose `written_at` disagrees with their class,
are rejected.
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

# dose-sacrifice-1's own scripts, pinned here. The FOUR upstream files (the world
# itself) are pinned inside dose-sacrifice-1's harness.py and asserted at import.
PINS = {
    "ncs1-explore-dose-sacrifice-1/scripts/harness.py":
        "543081c1896a66d0497f66b7ef7f5fec26e39e86d30e48939c09a54b879175ef",
    "ncs1-explore-dose-sacrifice-1/scripts/run_dose.py":
        "c7c83225c561cf86176a28302a44a1d6c99e92ec820fe4484b8d4380a9d14e2c",
    "ncs1-explore-dose-sacrifice-1/scripts/test_offline.py":
        "ea14b2a2db9b48a60a0fafc84c1dca8ca05b0d9b313a14df884a0870d60bf101",
    "ncs1-explore-dose-sacrifice-1/scripts/stats_lib.py":
        "bc8f984d29206272eb8851ce025aaa16b9eea6ac3838d234355cc8a6b0a2ba84",
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
    """The registry root that holds dose-sacrifice-1's scripts (which then resolve
    their own root for the merged world chain)."""
    for c in _root_candidates():
        if all((c / rel).exists() for rel in PINS):
            return c
    raise RuntimeError(
        "could not locate a registry root holding ncs1-explore-dose-sacrifice-1/scripts; "
        "set NCS1_REGISTRY_ROOT"
    )


REGISTRY = resolve_registry()
DOSE_SCRIPTS = REGISTRY / "ncs1-explore-dose-sacrifice-1" / "scripts"

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


# Loaded under the name `harness` so dose-sacrifice-1's own `run_dose.py` and
# `test_offline.py` (`import harness as H`) resolve to this exact object.
sys.path.insert(0, str(DOSE_SCRIPTS))
DH = _load("harness", DOSE_SCRIPTS / "harness.py")

R = DH.R  # realpeers-1's module: the world
MODELS: dict[str, str] = R.MODELS
BATCH_SIZE: int = R.BATCH_SIZE
Branch = R.Branch
Budget = R.Budget
run_worker = R.run_worker
entry_of = R.entry_of
entry_for_branch = DH.entry_for_branch
DEEPSEEK = DH.DEEPSEEK

# ------------------------------------------------------------------ the k-space
#
# Seat p of block k is uid = 8k + (p-1); instance = 500 + uid, with a
# deterministic 30% destruction draw and a deterministic candidate string per
# uid. Spent so far in the lineage:
#   realpeers-1        k =    0.. 29
#   realpeers-2        k =  100..499, 600..639
#   dose-sacrifice-1   k = 1000..1059 (free), 1200..1306 (assigned)
# This record starts at k = 5000. ONE episode per k, at position m+1 <= 8, so a
# whole 8-uid block is reserved for a single live agent and no instance, no
# candidate string and no destruction draw is shared with anything.
K0 = 5000
EPISODES_PER_CELL = 40
SCHEDULE_SEED = 0

# Series A "pure": m = 0..7, all-PROBED (net +m) or all-DECLINED (net -m).
# m = 0 is the single shared empty-log cell, so A has 15 cells, not 16.
A_M_MAX = 7
# Series B "mixed, length 4": d PROBED + (4-d) DECLINED.
B_LEN = 4

# Series C "the full composition grid": every (d PROBED, r DECLINED) with
# d + r <= C_M_MAX, including (0, 0). 36 cells x 40 = 1440 episodes, on a FRESH
# k-space (6000..7439) and a fresh schedule seed, so no draw and no instance is
# shared with series A/B.
K0_C = 6000
C_M_MAX = 7
SCHEDULE_SEED_C = 1

POOL_SOURCES = (
    # (label, registry-relative dir, glob, seat kind)
    ("realpeers-1", "ncs1-explore-sacrifice-realpeers-1/runs/deepseek", "k*/w1.json", "seat1"),
    ("realpeers-1", "ncs1-explore-sacrifice-realpeers-1/runs/deepseek", "k*/visible/w*.json", "visible"),
    ("realpeers-2", "ncs1-explore-sacrifice-realpeers-2/runs/deepseek", "k*/w1.json", "seat1"),
    ("realpeers-2", "ncs1-explore-sacrifice-realpeers-2/runs/deepseek", "k*/visible/w*.json", "visible"),
    ("dose-free", "ncs1-explore-dose-sacrifice-1/runs/deepseek", "k*/w1.json", "seat1"),
    ("dose-free", "ncs1-explore-dose-sacrifice-1/runs/deepseek", "k*/visible/w*.json", "visible"),
    ("dose-assigned", "ncs1-explore-dose-sacrifice-1/runs/assigned", "k*/visible/w*.json", "visible"),
)


def instance_of(k: int, position: int) -> int:
    """The harness's own seat -> instance map, replicated read-only for the
    collision assertions (realpeers-1 owns the real one)."""
    return 500 + k * BATCH_SIZE + (position - 1)


# ---------------------------------------------------------------------- cells


def cells() -> list[dict[str, Any]]:
    """The 20 cells, in the fixed order that allocates the k-space."""
    out: list[dict[str, Any]] = [{"series": "A", "cell": "A_m0", "d": 0, "r": 0}]
    for m in range(1, A_M_MAX + 1):
        out.append({"series": "A", "cell": f"A_probed{m}", "d": m, "r": 0})
    for m in range(1, A_M_MAX + 1):
        out.append({"series": "A", "cell": f"A_declined{m}", "d": 0, "r": m})
    for d in range(0, B_LEN + 1):
        out.append({"series": "B", "cell": f"B_d{d}", "d": d, "r": B_LEN - d})
    return _finish_cells(out)


def cells_C() -> list[dict[str, Any]]:
    """Series C — the FULL composition grid: every (d PROBED, r DECLINED) with
    d + r <= C_M_MAX, including the empty log (0, 0).

    Series A walks the two edges of this grid (r = 0 and d = 0) and series B
    walks its d + r = 4 anti-diagonal; C fills the interior, so `net` and the
    composition that produced it can finally be separated everywhere rather than
    at three isolated pairs. 36 cells, in the fixed order that allocates the
    k-space (row-major in d, then r).
    """
    out: list[dict[str, Any]] = []
    for d in range(0, C_M_MAX + 1):
        for r in range(0, C_M_MAX + 1 - d):
            out.append({"series": "C", "cell": f"C_d{d}r{r}", "d": d, "r": r})
    return _finish_cells(out)


def _finish_cells(out: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for c in out:
        c["m"] = c["d"] + c["r"]
        c["net"] = c["d"] - c["r"]
        c["position"] = c["m"] + 1
    return out


def all_cells() -> list[dict[str, Any]]:
    return cells() + cells_C()


# ---------------------------------------------------------------------- pools


def load_pools(registry: pathlib.Path | None = None,
               sources=POOL_SOURCES) -> dict[str, list[dict[str, Any]]]:
    """PROBED / DECLINED pools of real DeepSeek lines, as `Branch` entries."""
    roots = [registry] if registry else _root_candidates()
    pools: dict[str, list[dict[str, Any]]] = {"probed": [], "declined": []}
    for label, rel, glob, seat in sources:
        # The rollouts are gitignored, so a source may live in a different
        # checkout of the registry than the merged scripts do. Take the first
        # root that has it.
        d = next((root / rel for root in roots if (root / rel).exists()), None)
        if d is None:
            raise RuntimeError(f"pool source missing in every registry root: {rel}")
        for p in sorted(d.glob(glob)):
            row = json.loads(p.read_text())
            if row.get("model") != DEEPSEEK:
                continue
            if row.get("branch") == "hidden":  # never served to anybody
                continue
            if not row.get("note_written_at"):
                continue
            if row.get("probe_attempted"):
                kind, want = "probed", "probe"
            elif row.get("finalized"):
                kind, want = "declined", "finalize"
            else:
                continue
            if row["note_written_at"] != want:
                raise RuntimeError(f"{p}: written_at {row['note_written_at']!r} != {want!r}")
            text = (row.get("note_text") or "").strip()
            if not text:
                continue
            pools[kind].append({
                "instance": row["instance"],
                "position": row["position"],
                "written_at": row["note_written_at"],
                "text": text,
                "_source": label,
                "_seat": seat,
                "_source_k": row["k"],
            })
    for kind, rows in pools.items():
        insts = [e["instance"] for e in rows]
        if len(set(insts)) != len(insts):
            raise RuntimeError(f"duplicate instance ids in the {kind} pool")
    both = {e["instance"] for e in pools["probed"]} & {e["instance"] for e in pools["declined"]}
    if both:
        raise RuntimeError(f"instance id in both pools: {sorted(both)}")
    return pools


# ------------------------------------------------------------------- schedule


def build_schedule(pools: dict[str, list[dict[str, Any]]] | None = None,
                   seed: int = SCHEDULE_SEED,
                   per_cell: int = EPISODES_PER_CELL) -> list[dict[str, Any]]:
    """Series A + B: one dict per EPISODE, deterministic in `seed`."""
    return _build(cells(), K0, pools, seed, per_cell)


def build_schedule_C(pools: dict[str, list[dict[str, Any]]] | None = None,
                     seed: int = SCHEDULE_SEED_C,
                     per_cell: int = EPISODES_PER_CELL) -> list[dict[str, Any]]:
    """Series C: the full composition grid, on its own k-space and its own seed
    (so the draws are independent of A/B's rather than a replay of them)."""
    return _build(cells_C(), K0_C, pools, seed, per_cell)


def build_schedule_all(pools: dict[str, list[dict[str, Any]]] | None = None
                       ) -> list[dict[str, Any]]:
    pools = pools or load_pools()
    return build_schedule(pools) + build_schedule_C(pools)


def _build(cell_list: list[dict[str, Any]],
           k0: int,
           pools: dict[str, list[dict[str, Any]]] | None,
           seed: int,
           per_cell: int) -> list[dict[str, Any]]:
    """One dict per EPISODE, deterministic in `seed`.

    Sampling is WITHOUT replacement within a log (an episode never plants the
    same line twice) and WITH replacement across logs (the pools are small
    relative to the thousands of planted lines a schedule needs). The order of
    the planted lines inside a log is shuffled, so PROBED lines are not
    systematically first.
    """
    pools = pools or load_pools()
    pool_instances = {e["instance"] for e in pools["probed"] + pools["declined"]}
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    k = k0
    for cell in cell_list:
        for rep in range(per_cell):
            chosen = (rng.sample(pools["probed"], cell["d"])
                      + rng.sample(pools["declined"], cell["r"]))
            rng.shuffle(chosen)
            position = cell["position"]
            live = instance_of(k, position)
            planted = [e["instance"] for e in chosen]
            if len(set(planted)) != len(planted):
                raise RuntimeError(f"k{k}: repeated planted instance id")
            if live in pool_instances:
                raise RuntimeError(f"k{k}: live instance {live} collides with the pool")
            if live in set(planted):
                raise RuntimeError(f"k{k}: live instance {live} collides with a planted line")
            out.append({
                "k": k,
                "rep": rep,
                "series": cell["series"],
                "cell": cell["cell"],
                "d": cell["d"],
                "r": cell["r"],
                "m": cell["m"],
                "net": cell["net"],
                "position": position,
                "instance": live,
                "prefill": chosen,
            })
            k += 1
    return out
