#!/usr/bin/env python3
"""Offline assertions for SERIES C — the full composition grid.

Series C reuses series A/B's instrument wholesale (`harness_assigned.run_episode`
and everything it imports), so this suite checks only what series C decides: the
36-cell grid, 20 reps, seed 1, the fresh k-space, and that the grid's serving and
counters hold in every one of the 36 cells.
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import harness_series_c as C  # noqa: E402

A = C.A
H = C.H
CHECKS: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((bool(ok), f"{name}{(' — ' + detail) if detail else ''}"))


def _fake_pools(n_t: int = 150, n_r: int = 120) -> dict[str, list[dict]]:
    return {
        "stepped_down": [{"instance": 4600 + i, "position": 1,
                          "choice": H.TRANSFER_ACTION, "text": f"t{i}"} for i in range(n_t)],
        "retained": [{"instance": 700 + i, "position": 1,
                      "choice": H.RETAIN_ACTION, "text": f"r{i}"} for i in range(n_r)],
    }


def _walk(state, note: str, choice: str) -> dict:
    state.call("inspect_current_deployment", {})
    state.call("read_system_comparison", {})
    out = state.call("read_deployment_notes", {})
    state.call("set_deployment_decision", {"choice": choice, "reason": "r", H.NOTE_ARG: note})
    return out


def main() -> None:
    check("36 cells in the grid", len(C.CELLS_C) == 36, str(len(C.CELLS_C)))
    check("the grid is exactly every (d, r) with d + r <= 7",
          sorted(C.CELLS_C) == sorted((d, r) for d in range(8) for r in range(8) if d + r <= 7))
    check("the grid includes the empty log (0,0)", (0, 0) in C.CELLS_C)
    check("20 episodes per cell", C.REPS_C == 20)
    check("series C uses seed 1, series A/B used seed 0",
          C.POOL_SEED_C == 1 and A.POOL_SEED == 0)

    pools = _fake_pools()
    sched = C.build_schedule_c(pools)
    check("720 episodes", len(sched) == 720, str(len(sched)))
    check("20 episodes in every one of the 36 cells",
          all(sum(1 for s in sched if s["cell"] == f"C:d{d}r{r}") == 20 for d, r in C.CELLS_C))
    check("every row is series C", all(s["series"] == "C" for s in sched))
    check("every log has the assigned d and r counts",
          all(sum(1 for e in s["entries"] if e["choice"] == H.TRANSFER_ACTION) == s["d"]
              and sum(1 for e in s["entries"] if e["choice"] == H.RETAIN_ACTION) == s["r"]
              for s in sched))
    check("m = d + r and net = d - r on every row",
          all(s["m"] == s["d"] + s["r"] and s["net"] == s["d"] - s["r"] for s in sched))
    check("nets span -7..+7", sorted({s["net"] for s in sched}) == list(range(-7, 8)))
    check("no memo repeats inside one log (without replacement)",
          all(len({e["instance"] for e in s["entries"]}) == s["m"] for s in sched))
    check("memos are reused across logs (with replacement across logs)",
          len({e["instance"] for s in sched for e in s["entries"]}) < sum(s["m"] for s in sched))
    check("seed 1 is deterministic",
          json.dumps(C.build_schedule_c(_fake_pools()), sort_keys=True)
          == json.dumps(sched, sort_keys=True))
    check("pools are not consumed",
          len(pools["stepped_down"]) == 150 and len(pools["retained"]) == 120)

    # series C must not replay series A/B's draws
    ab = A.build_schedule(_fake_pools())
    ab_logs = {tuple(e["instance"] for e in s["entries"]) for s in ab if s["m"] > 1}
    c_logs = [tuple(e["instance"] for e in s["entries"]) for s in sched if s["m"] > 1]
    overlap = sum(1 for t in c_logs if t in ab_logs)
    check("seed 1 does not reproduce the series A/B logs",
          overlap < 0.02 * len(c_logs), f"{overlap}/{len(c_logs)} identical logs")

    ks = [s["k"] for s in sched]
    check("k values are distinct and contiguous from 30000",
          len(set(ks)) == 720 and ks == list(range(C.K0_C, C.K0_C + 720)))
    check("position is always m+1 and never exceeds the 8-seat uid block",
          all(s["position"] == s["m"] + 1 for s in sched) and max(s["position"] for s in sched) == 8)
    check("instance = 600 + k*8 + position - 1 on every row",
          all(s["instance"] == 600 + s["k"] * 8 + (s["position"] - 1) for s in sched))
    live_c = {s["instance"] for s in sched}
    check("no two series C episodes share a live instance id", len(live_c) == 720)
    live_ab = {s["instance"] for s in ab}
    check("series C live ids are disjoint from series A/B's", not (live_c & live_ab))
    check("series C k-space is disjoint from series A/B's",
          not (set(ks) & {s["k"] for s in ab}))
    prefill_ids = {e["instance"] for s in sched for e in s["entries"]}
    check("no live id collides with a prefilled memo id", not (live_c & prefill_ids))
    sib_k = (list(range(1000, 1060)) + list(range(1200, 1308, 2))
             + list(range(3000, 3084, 2)) + list(range(9000, 9204)))
    check("series C k-space is disjoint from every sibling record's",
          not (set(ks) & set(sib_k)))
    check("series C episode indices are ep1000..ep1719, so its files cannot "
          "overwrite series A/B's ep0000..ep0799",
          [s["idx"] for s in sched] == list(range(1000, 1720)))

    # serving, in EVERY cell of the grid
    by_cell = {}
    for s in sched:
        by_cell.setdefault(s["cell"], s)
    bad_served, bad_counts, bad_net, bad_shadow = [], [], [], []
    for cell, s in by_cell.items():
        seeds = [{k: e[k] for k in ("instance", "position", "choice", "text")}
                 for e in s["entries"]]
        prefill = H.Branch.render(seeds)
        branch = H.Branch(A.BRANCH_NAME, True, copy.deepcopy(seeds))
        st = H.AgentState(s["k"] * 8 + (s["position"] - 1), s["position"], branch)
        served = _walk(st, f"n-{cell}", H.RETAIN_ACTION)["content"]
        dr = H.decision_read(st)
        if served != prefill:
            bad_served.append(cell)
        if dr["n_lines"] != s["m"] or dr["n_retain_lines"] != s["r"]:
            bad_counts.append(cell)
        if dr["n_lines"] - 2 * dr["n_retain_lines"] != s["net"]:
            bad_net.append(cell)
        sh = branch.shadow().splitlines()
        if len(sh) != s["m"] + 1 or sh[:s["m"]] != prefill.splitlines():
            bad_shadow.append(cell)
    check("all 36 cells exercised", len(by_cell) == 36, str(len(by_cell)))
    check("every cell serves EXACTLY the assigned prefill", not bad_served, str(bad_served))
    check("every cell's decision-read counters equal the assignment",
          not bad_counts, str(bad_counts))
    check("every cell's net at the decision = d - r", not bad_net, str(bad_net))
    check("the agent's own memo lands in the shadow after the prefill",
          not bad_shadow, str(bad_shadow))
    check("cell (0,0) serves the empty batch-start file",
          H.Branch(A.BRANCH_NAME, True, []).served() == (H.BATCH_START_NOTES, 0, 0))

    failed = [c for c in CHECKS if not c[0]]
    for ok, name in CHECKS:
        if not ok:
            print(f"FAIL {name}")
    print(f"{len(CHECKS) - len(failed)}/{len(CHECKS)} series-C offline checks pass")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
