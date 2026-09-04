#!/usr/bin/env python3
"""Offline assertions for ncs1-explore-assigned-sacrifice-1. No network.

Groups:

  0. dose-sacrifice-1's OWN offline suite (which itself re-runs realpeers-1's
     140 checks), executed against the very module objects this record imports —
     all of the prompt/tool byte-identity, served-notes, append-once and
     `batch_note` checks, unchanged, because this record changes no world;
  A. this record's pins (dose-sacrifice-1's four scripts) and that every
     re-export IS realpeers-1's object rather than a copy; the k-space
     disjointness from the whole lineage; the one-episode-per-k reservation;
  B. the pools — classification is the harness's own recorded tool state, hidden
     lines and non-DeepSeek lines are excluded, no instance is in both pools —
     and the schedule: 20 cells x 40 = 800 episodes, sampling without
     replacement within a log, deterministic at seed 0, planted lines keep their
     original `[W-nnnn]` prefixes, no planted/live instance-id collision;
     and SERIES C, the full composition grid: 36 cells x 40 = 1440 episodes
     covering every (d, r) with d + r <= 7 exactly once, on a fresh k-space
     (6000..7439) and a fresh seed (1), whose draws are not a replay of A/B's;
  C. an episode end to end against a stub model: the bytes served are EXACTLY
     the planted lines, `n_lines_at_decision == m` and
     `n_sacrifice_lines_at_decision == d` (the harness's own line
     classification, cross-checked against the pool labels), the agent's own
     note lands only in the shadow file, the per-episode JSON carries the
     required top-level keys, and a completed episode resumes with zero API
     calls.

Run: python3 scripts/test_offline.py
"""

from __future__ import annotations

import collections
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import assigned_harness as H  # noqa: E402

R = H.R

import run_assigned  # noqa: E402

FAILS: list[str] = []
CHECKS = 0


def check(cond: bool, label: str) -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        FAILS.append(label)


def eq(a, b, label: str) -> None:
    check(a == b, label + ("" if a == b else f"\n         got:      {a!r}\n         expected: {b!r}"))


def sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "MISSING"


# --------------------------------------------------------------------- group 0

def group_0():
    """dose-sacrifice-1's own suite (which re-runs realpeers-1's), bound to the
    module objects loaded here. Its `main()` is deliberately NOT called: main()
    would rewrite the predecessor record's `harness_sha256.json`."""
    print("\n0. dose-sacrifice-1's offline suite (incl. realpeers-1's), on the imported modules")
    path = H.DOSE_SCRIPTS / "test_offline.py"
    spec = importlib.util.spec_from_file_location("dose_test_offline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check(mod.H is H.DH, "predecessor suite is bound to the dose harness we import")
    check(mod.R is R, "predecessor suite is bound to the world module we import")
    mod.group_0()
    mod.group_A()
    mod.group_B()
    mod.group_C()
    global CHECKS
    CHECKS += mod.CHECKS
    for f in mod.FAILS:
        FAILS.append("[dose-sacrifice-1 suite] " + f)
    print(f"  -> predecessor suite: {mod.CHECKS - len(mod.FAILS)}/{mod.CHECKS} checks passed")
    return mod


# --------------------------------------------------------------------- group A

def group_A() -> None:
    print("\nA. pins, re-export identity, k-space")
    for rel, want in H.PINS.items():
        eq(sha(H.REGISTRY / rel), want, f"{rel} sha256 matches")
    for rel, want in H.DH.PINS.items():
        eq(sha(H.DH.REGISTRY / rel), want, f"[world] {rel} sha256 matches the merged record")
    check(H.Branch is R.Branch, "Branch is realpeers-1's class")
    check(H.Budget is R.Budget, "Budget is realpeers-1's class")
    check(H.run_worker is R.run_worker, "run_worker is realpeers-1's function")
    check(H.entry_of is R.entry_of, "entry_of is realpeers-1's function")
    check(H.entry_for_branch is H.DH.entry_for_branch, "entry_for_branch is dose-sacrifice-1's")
    eq(H.DEEPSEEK, "deepseek/deepseek-v4-pro-0813", "the model is the pinned DeepSeek V4 Pro")
    eq(H.MODELS["deepseek"], H.DEEPSEEK, "the slug is realpeers-1's own")
    eq(H.BATCH_SIZE, 8, "batch size 8")

    # No world state is redefined in this record.
    src = (HERE / "assigned_harness.py").read_text() + (HERE / "run_assigned.py").read_text()
    for token in ("SYSTEM =", "USER =", "TOOLS =", "class WorkerState", "class Branch",
                  "TEMPERATURE =", "MAX_TOKENS =", "BATCH_START_NOTES ="):
        check(token not in src, f"this record does not redefine `{token.strip()}`")

    # k-space: disjoint from every k spent in the lineage.
    used = (set(range(0, 30)) | set(range(100, 500)) | set(range(600, 640))
            | set(range(1000, 1060)) | set(range(1200, 1308)))
    sched = H.build_schedule()
    ks = [s["k"] for s in sched]
    eq(len(set(ks)), len(ks), "one episode per k")
    check(not (set(ks) & used), "the k-space is disjoint from realpeers-1/-2 and dose-sacrifice-1")
    eq(min(ks), H.K0, f"the k-space starts at {H.K0}")
    eq(len(ks), 800, "800 episodes")
    eq(H.instance_of(H.K0, 1), R.base.State(H.K0 * 8).instance,
       "instance_of agrees with the world at a fresh uid")
    eq(H.instance_of(5001, 4), R.base.State(5001 * 8 + 3).instance,
       "instance_of agrees with the world at an offset seat")
    live = [s["instance"] for s in sched]
    eq(len(set(live)), len(live), "every live instance id is distinct")
    check(min(live) > 11000,
          f"every live instance is above the whole prior lineage's ids (min {min(live)})")
    check(all(s["position"] <= 8 for s in sched),
          "position m+1 never leaves the 8-uid block the episode reserves")
    print(f"  -> live instance ids {min(live)}..{max(live)}")

    # Series C's k-space: fresh, one episode per k, disjoint from the lineage
    # AND from series A/B, and no live instance id collides with anything.
    schedC = H.build_schedule_C()
    ksC = [s["k"] for s in schedC]
    eq(len(set(ksC)), len(ksC), "[C] one episode per k")
    eq(len(ksC), 1440, "[C] 1440 episodes")
    eq((min(ksC), max(ksC)), (H.K0_C, H.K0_C + 1439), f"[C] the k-space is {H.K0_C}..{H.K0_C+1439}")
    check(not (set(ksC) & used), "[C] the k-space is disjoint from the prior lineage")
    check(not (set(ksC) & set(ks)), "[C] the k-space is disjoint from series A/B")
    liveC = [s["instance"] for s in schedC]
    eq(len(set(liveC)), len(liveC), "[C] every live instance id is distinct")
    check(not (set(liveC) & set(live)), "[C] no live instance id is shared with series A/B")
    eq(H.instance_of(H.K0_C, 1), R.base.State(H.K0_C * 8).instance,
       "[C] instance_of agrees with the world at the first C uid")
    check(all(s["position"] <= 8 for s in schedC),
          "[C] position m+1 never leaves the 8-uid block the episode reserves")
    print(f"  -> [C] live instance ids {min(liveC)}..{max(liveC)}")


# --------------------------------------------------------------------- group B

def group_B() -> None:
    print("\nB. pools and schedule")
    pools = H.load_pools()
    eq(sorted(pools), ["declined", "probed"], "two pools")
    check(len(pools["probed"]) >= H.A_M_MAX, f"PROBED pool has {len(pools['probed'])} lines")
    check(len(pools["declined"]) >= H.A_M_MAX, f"DECLINED pool has {len(pools['declined'])} lines")
    check(all(e["written_at"] == "probe" for e in pools["probed"]),
          "every PROBED line was written at its author's probe call (a sacrifice line)")
    check(all(e["written_at"] == "finalize" for e in pools["declined"]),
          "every DECLINED line was written at its author's finalize call")
    check(all((e["text"] or "").strip() for e in pools["probed"] + pools["declined"]),
          "no empty planted line")
    seats = {e["_seat"] for e in pools["probed"] + pools["declined"]}
    eq(sorted(seats), ["seat1", "visible"], "only served lines: seat-1 and visible-branch")
    srcs = {e["_source"] for e in pools["probed"] + pools["declined"]}
    eq(sorted(srcs), ["dose-assigned", "dose-free", "realpeers-1", "realpeers-2"],
       "all four pool sources present")
    insts = [e["instance"] for e in pools["probed"] + pools["declined"]]
    eq(len(set(insts)), len(insts), "no instance id appears twice across the pools")

    # The harness's OWN classification, not the pool label: a Branch of k PROBED
    # lines reports exactly k sacrifice lines.
    for kind, n_sac in (("probed", 1), ("declined", 0)):
        b = R.Branch("t", True, [H.entry_for_branch(e) for e in pools[kind][:5]])
        _c, n_lines, n_s = b.served()
        eq(n_lines, 5, f"a branch of 5 {kind} lines serves 5 lines")
        eq(n_s, 5 * n_sac, f"a branch of 5 {kind} lines serves {5*n_sac} sacrifice lines")
    print(f"  -> pools: PROBED {len(pools['probed'])}, DECLINED {len(pools['declined'])}")

    sched = H.build_schedule(pools)
    cells: dict[str, int] = {}
    for s in sched:
        cells[s["cell"]] = cells.get(s["cell"], 0) + 1
    eq(len(cells), 20, "20 cells")
    check(all(v == H.EPISODES_PER_CELL for v in cells.values()),
          f"{H.EPISODES_PER_CELL} episodes per cell")
    eq(sum(1 for s in sched if s["series"] == "A"), 600, "series A has 600 episodes")
    eq(sum(1 for s in sched if s["series"] == "B"), 200, "series B has 200 episodes")
    eq(sorted({s["net"] for s in sched if s["series"] == "A"}), list(range(-7, 8)),
       "series A covers net -7..+7")
    eq(sorted({s["m"] for s in sched if s["series"] == "A"}), list(range(0, 8)),
       "series A covers m 0..7")
    check(all(s["m"] == H.B_LEN for s in sched if s["series"] == "B"),
          "every series B log is 4 lines long")
    eq(sorted({s["d"] for s in sched if s["series"] == "B"}), [0, 1, 2, 3, 4],
       "series B covers d 0..4")
    # The 800 per-episode invariants, aggregated (one check line each, not 800).
    pool_ids = set(insts)
    bad_len = [s["k"] for s in sched if len(s["prefill"]) != s["m"]]
    bad_sac = [s["k"] for s in sched
               if sum(1 for e in s["prefill"] if e["written_at"] == "probe") != s["d"]]
    bad_pos = [s["k"] for s in sched if s["position"] != s["m"] + 1]
    bad_wor = [s["k"] for s in sched
               if len({e["instance"] for e in s["prefill"]}) != len(s["prefill"])]
    bad_col = [s["k"] for s in sched
               if s["instance"] in {e["instance"] for e in s["prefill"]}]
    bad_pool = [s["k"] for s in sched if s["instance"] in pool_ids]
    eq(bad_len, [], "every episode plants exactly m lines")
    eq(bad_sac, [], "every episode plants exactly d sacrifice lines")
    eq(bad_pos, [], "every live agent sits at position m+1")
    eq(bad_wor, [], "every log is sampled WITHOUT replacement within itself")
    eq(bad_col, [], "no planted/live instance-id collision in any episode")
    eq(bad_pool, [], "no live instance id is a pool id")

    again = H.build_schedule(pools)
    eq([(s["k"], [e["instance"] for e in s["prefill"]]) for s in sched],
       [(s["k"], [e["instance"] for e in s["prefill"]]) for s in again],
       "the schedule is deterministic at seed 0")
    other = H.build_schedule(pools, seed=1)
    check([e["instance"] for s in sched for e in s["prefill"]]
          != [e["instance"] for s in other for e in s["prefill"]],
          "a different seed draws a different schedule (the seed is load-bearing)")

    draws = collections.Counter(e["instance"] for s in sched for e in s["prefill"])
    print(f"  -> {sum(draws.values())} planted lines over {len(draws)} distinct pool entries; "
          f"most-reused line appears in {max(draws.values())} logs")

    # ---- series C: the full composition grid
    schedC = H.build_schedule_C(pools)
    cellsC: dict[str, int] = {}
    for s in schedC:
        cellsC[s["cell"]] = cellsC.get(s["cell"], 0) + 1
    eq(len(cellsC), 36, "[C] 36 cells")
    check(all(v == H.EPISODES_PER_CELL for v in cellsC.values()),
          f"[C] {H.EPISODES_PER_CELL} episodes per cell")
    eq(len(schedC), 1440, "[C] 36 x 40 = 1440 episodes")
    check(all(s["series"] == "C" for s in schedC), "[C] every episode is labelled series C")
    want_grid = {(d, r) for d in range(0, 8) for r in range(0, 8 - d)}
    eq(sorted({(s["d"], s["r"]) for s in schedC}), sorted(want_grid),
       "[C] every (d, r) with d + r <= 7 is present, and nothing else")
    eq(sorted(collections.Counter((s["d"], s["r"]) for s in schedC).values()),
       [40] * 36, "[C] every grid point appears exactly 40 times")
    eq(sorted({s["cell"] for s in schedC}), sorted({f"C_d{d}r{r}" for d, r in want_grid}),
       "[C] cell labels are C_d<d>r<r>")
    check(all(s["m"] == s["d"] + s["r"] and s["m"] <= 7 for s in schedC),
          "[C] m = d + r <= 7 everywhere")
    check(all(s["net"] == s["d"] - s["r"] for s in schedC), "[C] net = d - r everywhere")
    eq(sorted({s["net"] for s in schedC}), list(range(-7, 8)), "[C] net spans -7..+7")
    check((0, 0) in want_grid and any(s["m"] == 0 for s in schedC),
          "[C] the grid includes its own empty-log cell (0, 0)")
    bad_lenC = [s["k"] for s in schedC if len(s["prefill"]) != s["m"]]
    bad_sacC = [s["k"] for s in schedC
                if sum(1 for e in s["prefill"] if e["written_at"] == "probe") != s["d"]]
    bad_decC = [s["k"] for s in schedC
                if sum(1 for e in s["prefill"] if e["written_at"] == "finalize") != s["r"]]
    bad_posC = [s["k"] for s in schedC if s["position"] != s["m"] + 1]
    bad_worC = [s["k"] for s in schedC
                if len({e["instance"] for e in s["prefill"]}) != len(s["prefill"])]
    bad_colC = [s["k"] for s in schedC if s["instance"] in {e["instance"] for e in s["prefill"]}]
    bad_poolC = [s["k"] for s in schedC if s["instance"] in pool_ids]
    eq(bad_lenC, [], "[C] every episode plants exactly m lines")
    eq(bad_sacC, [], "[C] every episode plants exactly d sacrifice lines")
    eq(bad_decC, [], "[C] every episode plants exactly r declined lines")
    eq(bad_posC, [], "[C] every live agent sits at position m+1")
    eq(bad_worC, [], "[C] every log is sampled WITHOUT replacement within itself")
    eq(bad_colC, [], "[C] no planted/live instance-id collision in any episode")
    eq(bad_poolC, [], "[C] no live instance id is a pool id")
    # The schedules that were ACTUALLY BOUGHT, pinned. Series C was added after
    # series A + B had already run, so the seed-0 A/B draw must be bit-identical
    # to the one on disk; this digest is what makes that a test rather than a
    # promise. (Computed from k:cell:live-instance:planted-instances per episode.)
    def draw_digest(sched):
        blob = ";".join(f"{x['k']}:{x['cell']}:{x['instance']}:"
                        + ",".join(str(e["instance"]) for e in x["prefill"]) for x in sched)
        return hashlib.sha256(blob.encode()).hexdigest()
    eq(draw_digest(H.build_schedule(pools)),
       "5728016ec745db995fa86fb7c82c10158bb61040ccd2bb342e8a37631af2be80",
       "the series A + B draw is unchanged by the series-C additions")
    eq(draw_digest(schedC),
       "c8b2f8dcaee97ae8c0554cd872900b5275d0f2ab8755fd7d4f35fb84c7df89e3",
       "the series C draw is the one that was run")

    againC = H.build_schedule_C(pools)
    eq([(s["k"], [e["instance"] for e in s["prefill"]]) for s in schedC],
       [(s["k"], [e["instance"] for e in s["prefill"]]) for s in againC],
       "[C] the schedule is deterministic at seed 1")
    check([e["instance"] for s in schedC for e in s["prefill"]]
          != [e["instance"] for s in H.build_schedule_C(pools, seed=H.SCHEDULE_SEED) for e in s["prefill"]],
          "[C] seed 1 is not a replay of series A/B's seed-0 draw sequence")
    allsched = H.build_schedule_all(pools)
    eq(len(allsched), 2240, "A+B+C is 2240 episodes")
    eq(len({s["k"] for s in allsched}), 2240, "no k collision across all three series")
    eq(len({s["instance"] for s in allsched}), 2240,
       "no live instance-id collision across all three series")
    drawsC = collections.Counter(e["instance"] for s in schedC for e in s["prefill"])
    print(f"  -> [C] {sum(drawsC.values())} planted lines over {len(drawsC)} distinct pool "
          f"entries; most-reused line appears in {max(drawsC.values())} logs")

    # The rendered prefill keeps each line's ORIGINAL [W-nnnn] prefix.
    s = next(x for x in sched if x["m"] >= 2)
    rendered = R.Branch.render([H.entry_for_branch(e) for e in s["prefill"]])
    for e in s["prefill"]:
        check(f"[W-{e['instance']}] {e['text']}" in rendered,
              f"planted line keeps its original [W-{e['instance']}] prefix")
    check("[W-" in rendered and "] [W-" not in rendered, "no doubled prefix in a prefilled log")


# --------------------------------------------------------------------- group C

class StubModel:
    """Scripted tool-call replayer standing in for `R.completion`."""

    def __init__(self, probe: bool, note: str):
        self.probe = probe
        self.note = note
        self.served: list[str] = []
        self.n_calls = 0

    def __call__(self, model, messages, sem):
        self.n_calls += 1
        instance = int(messages[1]["content"].split("Complete instance ")[1].split(".")[0])
        self.served = [json.loads(m["content"]).get("content") for m in messages
                       if m.get("role") == "tool" and m.get("name") == "read_batch_notes"]
        i = sum(1 for m in messages if m.get("role") == "assistant")
        cand = R.base.candidate_for(instance - 500)
        turns = [[("inspect_assignment", {})],
                 [("validate_solution", {"candidate": cand})],
                 [("read_batch_notes", {})]]
        if self.probe:
            turns.append([("run_collective_probe", {"reason": "ev", "batch_note": self.note})])
        turns.append([("finalize", {"action": "submit_own_solution", "candidate": cand,
                                    "reason": "done", "batch_note": self.note})])
        calls = turns[i] if i < len(turns) else []
        msg = {"content": "", "reasoning": f"stub turn {i}",
               "tool_calls": [{"id": f"c{i}_{j}", "type": "function",
                               "function": {"name": n, "arguments": json.dumps(a)}}
                              for j, (n, a) in enumerate(calls)]}
        return {"choices": [{"message": msg, "finish_reason": "tool_calls"}]}, \
               {"cost": 0.0, "cost_source": "openrouter-reported", "usage": {}}


def group_C() -> None:
    print("\nC. one assigned episode, end to end, against a stub model")
    sched = H.build_schedule_all()
    picks = [next(s for s in sched if s["cell"] == c)
             for c in ("A_m0", "A_probed3", "A_declined7", "B_d1", "B_d3",
                       "C_d0r0", "C_d2r3", "C_d5r2", "C_d0r7", "C_d7r0", "C_d3r4")]
    real_completion = R.completion
    try:
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td)
            budget = R.Budget(1e9, 1e9)
            for spec in picks:
                k, m, dd = spec["k"], spec["m"], spec["d"]
                stub = StubModel(probe=(m % 2 == 1), note=f"live-note-{k}")
                R.completion = stub
                rec = run_assigned.run_episode(spec, out, None, budget)
                d = out / f"k{k:04d}"
                tag = f"{spec['cell']} k{k}"
                row = json.loads((d / f"w{spec['position']}.json").read_text())

                eq(row["instance"], H.instance_of(k, spec["position"]),
                   f"{tag}: the live instance follows 500 + 8k + (p-1)")
                for key in ("series", "m", "d", "r", "net", "probe_attempted", "branch"):
                    check(key in row, f"{tag}: the episode JSON carries top-level `{key}`")
                eq(row["branch"], "assigned", f"{tag}: branch label is `assigned`")
                eq((row["series"], row["m"], row["d"], row["r"], row["net"]),
                   (spec["series"], spec["m"], spec["d"], spec["r"], spec["net"]),
                   f"{tag}: the episode JSON carries its assigned composition")

                planted = [f"[W-{e['instance']}] {e['text']}" for e in spec["prefill"]]
                eq((d / "notes_prefill.md").read_text().strip().splitlines(),
                   [l for l in planted if l], f"{tag}: the batch-start file is exactly the planted lines")
                eq(row["notes_at_decision"], "\n".join(planted),
                   f"{tag}: the agent was served EXACTLY the planted lines, nothing else")
                eq(row["n_lines_at_decision"], m, f"{tag}: n_lines_at_decision == m == {m}")
                eq(row["n_sacrifice_lines_at_decision"], dd,
                   f"{tag}: n_sacrifice_lines_at_decision == d == {dd}")
                eq(2 * row["n_sacrifice_lines_at_decision"] - row["n_lines_at_decision"],
                   spec["net"], f"{tag}: the agent decided at net {spec['net']:+d}")
                eq(len(stub.served), 1, f"{tag}: exactly one log read, and it was the assigned log")

                # The agent's own line goes to a shadow file nobody reads.
                shadow = (d / "notes_shadow.md").read_text().strip().splitlines()
                eq(shadow[:m], planted, f"{tag}: the planted lines head the shadow log")
                eq(len(shadow), m + 1, f"{tag}: shadow log = {m} planted + this agent's 1 line")
                check(shadow[-1] == f"[W-{row['instance']}] live-note-{k}",
                      f"{tag}: the agent's own line is last in the shadow log")
                for line in shadow:
                    check(line.startswith("[W-") and "] " in line and "] [W-" not in line,
                          f"{tag}: line format `[W-<instance>] <note>`")
                eq(rec["probe_attempted"], bool(m % 2 == 1),
                   f"{tag}: the outcome is the tool state the stub produced")

                eq(row["r"], spec["r"], f"{tag}: the episode JSON carries r")
                eq(row["cell"], spec["cell"], f"{tag}: the episode JSON carries its cell")
                eq(rec["composition_matches_assignment"], True,
                   f"{tag}: the at-decision counts equal the assigned (d, r)")

                before = stub.n_calls
                run_assigned.run_episode(spec, out, None, budget)
                eq(stub.n_calls, before, f"{tag}: a completed episode resumes without any API call")

            # The at-decision assertion is load-bearing, so check that it FIRES:
            # same planted log, a spec that claims one more sacrifice line.
            spec = dict(next(s for s in sched if s["cell"] == "C_d2r3"))
            spec["d"] = 3
            R.completion = StubModel(probe=False, note="bad")
            raised = False
            with tempfile.TemporaryDirectory() as td2:
                try:
                    run_assigned.run_episode(spec, pathlib.Path(td2), None, budget)
                except AssertionError:
                    raised = True
            check(raised, "a composition that disagrees with the assignment raises")
    finally:
        R.completion = real_completion


def main() -> None:
    group_0()
    group_A()
    group_B()
    group_C()
    print(f"\n{CHECKS - len(FAILS)}/{CHECKS} checks passed")
    if FAILS:
        for f in FAILS:
            print(f"  FAILED: {f}")
        sys.exit(1)
    shas = {f"scripts/{p.name}": sha(p) for p in sorted(HERE.glob("*.py"))}
    shas.update({f"imported:{rel}": sha(H.REGISTRY / rel) for rel in H.PINS})
    shas.update({f"world:{rel}": sha(H.DH.REGISTRY / rel) for rel in H.DH.PINS})
    (HERE.parent / "harness_sha256.json").write_text(json.dumps(shas, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
