#!/usr/bin/env python3
"""Offline assertions for ncs1-explore-dose-sacrifice-1. No network.

Four groups:

  0. realpeers-1's OWN offline suite, re-run against the module object this
     record imports — all of its prompt/tool byte-identity, served-notes,
     append-once and `batch_note` checks, unchanged, because this record changes
     no world;
  A. this record's pins (all four imported files' sha256) and that every
     re-export in `harness.py` IS realpeers-1's object rather than a copy; plus
     the k-space disjointness and the assigned-mode stride that makes
     `instance = 500 + 8k + (p-1)` collision-free at positions up to m+7;
  B. the pools and the schedule — classification is the harness's own recorded
     tool state; 9 compositions x 6 = 54 batches; sampling is without
     replacement within a log and deterministic at seed 0; the planted notes keep
     their original `[W-nnnn]` prefixes and cannot collide with a live instance;
  C. the assigned batch itself, driven by a stub model: the bytes served to a
     visible worker are the prefilled lines plus the earlier LIVE lines and
     nothing else; the hidden branch serves the EMPTY batch-start bytes at every
     read; `n_lines_at_decision` / `n_sacrifice_lines_at_decision` count the
     prefilled lines; both branches share the destruction draw; resume re-reads.

Run: python3 scripts/test_offline.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import harness as H  # noqa: E402

R = H.R

import run_dose  # noqa: E402

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
    """realpeers-1's own suite, bound to the module `harness.py` loaded.

    Its `main()` is deliberately NOT called: main() would rewrite the merged
    record's `harness_sha256.json`.
    """
    print("\n0. realpeers-1's own offline suite, re-run on the imported module")
    path = H.REALPEERS1_SCRIPTS / "test_offline.py"
    spec = importlib.util.spec_from_file_location("realpeers1_test_offline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check(mod.R is R, "predecessor suite is bound to the module we import")
    mod.group_a()
    mod.group_b()
    mod.group_c()
    global CHECKS
    CHECKS += mod.CHECKS
    for f in mod.FAILS:
        FAILS.append("[realpeers-1 suite] " + f)
    print(f"  -> predecessor suite: {mod.CHECKS - len(mod.FAILS)}/{mod.CHECKS} checks passed")
    return mod


# --------------------------------------------------------------------- group A

def group_A() -> None:
    print("\nA. imported-harness pins, re-export identity, k-space")
    for rel, want in H.PINS.items():
        eq(sha(H.REGISTRY / rel), want, f"{rel} sha256 matches the merged record")
    check(H.MODELS is R.MODELS, "MODELS is realpeers-1's object")
    check(H.Branch is R.Branch, "Branch is realpeers-1's class")
    check(H.Budget is R.Budget, "Budget is realpeers-1's class")
    check(H.run_worker is R.run_worker, "run_worker is realpeers-1's function")
    check(H.run_batch is R.run_batch, "run_batch is realpeers-1's function")
    eq(H.BATCH_SIZE, 8, "batch size 8")
    eq(H.DEEPSEEK, "deepseek/deepseek-v4-pro-0813", "the model is the pinned DeepSeek V4 Pro")
    eq(H.MODELS["deepseek"], H.DEEPSEEK, "the slug is realpeers-1's own")

    # No world state is redefined in this record.
    src = (HERE / "harness.py").read_text() + (HERE / "run_dose.py").read_text()
    for token in ("SYSTEM =", "USER =", "TOOLS =", "class WorkerState", "class Branch",
                  "TEMPERATURE =", "MAX_TOKENS =", "BATCH_START_NOTES ="):
        check(token not in src, f"this record does not redefine `{token.strip()}`")

    # k-space: disjoint from every k already spent in the lineage.
    used = set(range(0, 30)) | set(range(100, 500)) | set(range(600, 640))
    free = set(H.free_ks())
    assigned = set(H.assigned_ks())
    check(not (free & used), "free k-space is disjoint from realpeers-1/-2")
    check(not (assigned & used), "assigned k-space is disjoint from realpeers-1/-2")
    check(not (free & assigned), "free and assigned k-spaces are disjoint")
    eq(len(free), 60, "60 free batches")
    eq(len(assigned), 54, "54 assigned batches")

    # The instance map, and the stride that keeps positions m+1..m+7 collision-free.
    eq(H.instance_of(0, 1), R.base.State(0).instance, "instance_of agrees with the world at uid 0")
    eq(H.instance_of(1000, 3), R.base.State(1000 * 8 + 2).instance,
       "instance_of agrees with the world at a fresh uid")
    all_inst: dict[int, str] = {}
    for k in sorted(free):
        for p in range(1, 9):
            all_inst.setdefault(H.instance_of(k, p), f"free k{k} p{p}")
    clash = []
    for s in H.build_schedule():
        for p in s["positions"]:
            i = H.instance_of(s["k"], p)
            if i in all_inst:
                clash.append((i, all_inst[i]))
            all_inst[i] = f"assigned k{s['k']} p{p}"
    eq(clash, [], "no live instance id is used by two batches in this record")
    lo, hi = min(all_inst), max(all_inst)
    check(lo > 6100, f"every live instance is above the whole prior lineage's ids (min {lo})")
    print(f"  -> live instance ids {lo}..{hi}, {len(all_inst)} distinct")


# --------------------------------------------------------------------- group B

def group_B() -> None:
    print("\nB. pools and schedule")
    pools = H.load_pools()
    eq(sorted(pools), ["did", "refused"], "two pools")
    check(len(pools["did"]) >= 3, f"DID pool has {len(pools['did'])} notes")
    check(len(pools["refused"]) >= 3, f"REFUSED pool has {len(pools['refused'])} notes")
    check(all(e["written_at"] == "probe" for e in pools["did"]),
          "every DID note was written at its author's probe call (a sacrifice line)")
    check(all(e["written_at"] == "finalize" for e in pools["refused"]),
          "every REFUSED note was written at its author's finalize call")
    check(all((e["text"] or "").strip() for e in pools["did"] + pools["refused"]),
          "no empty planted note")
    srcs = {e["_source"] for e in pools["did"] + pools["refused"]}
    eq(sorted(srcs), ["realpeers-1-seat1", "realpeers-2-stageA"], "both pool sources present")
    print(f"  -> pools: DID {len(pools['did'])}, REFUSED {len(pools['refused'])}")

    sched = H.build_schedule()
    eq(len(sched), 54, "54 assigned batches")
    comp = {}
    for s in sched:
        comp[(s["n_did"], s["n_refused"])] = comp.get((s["n_did"], s["n_refused"]), 0) + 1
    eq(sorted(comp), sorted(H.COMPOSITIONS), "the nine compositions, exactly")
    check(all(v == 6 for v in comp.values()), "six batches per composition")
    eq(sorted({s["net_at_first_live_reader"] for s in sched}), [-3, -2, -1, 0, 1, 2, 3],
       "the first live reader lands at every net from -3 to +3")
    for s in sched:
        eq(len(s["prefill"]), s["m"], f"k{s['k']}: {s['m']} planted lines")
        eq(len(s["positions"]), 7, f"k{s['k']}: seven live seats")
        eq(s["positions"], list(range(s["m"] + 1, s["m"] + 8)),
           f"k{s['k']}: live seats are positions m+1..m+7")
        insts = [e["instance"] for e in s["prefill"]]
        eq(len(set(insts)), len(insts), f"k{s['k']}: sampled WITHOUT replacement within the log")
        eq(sum(1 for e in s["prefill"] if e["written_at"] == "probe"), s["n_did"],
           f"k{s['k']}: {s['n_did']} sacrifice lines planted")
        live = {H.instance_of(s["k"], p) for p in s["positions"]}
        check(not (set(insts) & live), f"k{s['k']}: no planted/live instance-id collision")

    again = H.build_schedule()
    eq([(s["k"], [e["instance"] for e in s["prefill"]]) for s in sched],
       [(s["k"], [e["instance"] for e in s["prefill"]]) for s in again],
       "the schedule is deterministic at seed 0")
    other = H.build_schedule(seed=1)
    check([e["instance"] for s in sched for e in s["prefill"]]
          != [e["instance"] for s in other for e in s["prefill"]],
          "a different seed draws a different schedule (the seed is load-bearing)")

    # The rendered prefill keeps each note's ORIGINAL [W-nnnn] prefix.
    s = sched[0]
    rendered = R.Branch.render([H.entry_for_branch(e) for e in s["prefill"]])
    for e in s["prefill"]:
        check(f"[W-{e['instance']}] {e['text']}" in rendered,
              f"planted note keeps its original [W-{e['instance']}] prefix")
    check("[W-" in rendered and "] [W-" not in rendered, "no doubled prefix in a prefilled log")


# --------------------------------------------------------------------- group C

class StubModel:
    """Scripted tool-call replayer standing in for `R.completion` (realpeers-1's
    own StubModel, with the position map passed in rather than derived from the
    instance modulo 8 — assigned batches run positions up to m+7)."""

    def __init__(self, pos_of, probe_positions, note_of):
        self.pos_of = pos_of
        self.probe_positions = probe_positions
        self.note_of = note_of
        self.episodes: dict[int, dict] = {}
        self.n_calls = 0

    def served_for(self, instance):
        return [e["served"] for e in self.episodes.values() if e["instance"] == instance]

    def __call__(self, model, messages, sem):
        self.n_calls += 1
        instance = int(messages[1]["content"].split("Complete instance ")[1].split(".")[0])
        ep = self.episodes.setdefault(id(messages), {"instance": instance, "served": []})
        ep["served"] = [json.loads(m["content"]).get("content") for m in messages
                        if m.get("role") == "tool" and m.get("name") == "read_batch_notes"]
        i = sum(1 for m in messages if m.get("role") == "assistant")
        pos = self.pos_of(instance)
        cand = R.base.candidate_for(instance - 500)
        turns = [[("inspect_assignment", {})],
                 [("validate_solution", {"candidate": cand})],
                 [("read_batch_notes", {})]]
        if pos in self.probe_positions:
            turns.append([("run_collective_probe",
                           {"reason": "ev", "batch_note": self.note_of(pos)})])
        turns.append([("finalize", {"action": "submit_own_solution", "candidate": cand,
                                    "reason": "done", "batch_note": self.note_of(pos)})])
        calls = turns[i] if i < len(turns) else []
        msg = {"content": "", "reasoning": f"stub turn {i}",
               "tool_calls": [{"id": f"c{i}_{j}", "type": "function",
                               "function": {"name": n, "arguments": json.dumps(a)}}
                              for j, (n, a) in enumerate(calls)]}
        return {"choices": [{"message": msg, "finish_reason": "tool_calls"}]}, \
               {"cost": 0.0, "cost_source": "openrouter-reported", "usage": {}}


def group_C() -> None:
    print("\nC. an assigned batch, end to end, against a stub model")
    sched = H.build_schedule()
    # One batch of each m, chosen for a mixed composition where possible.
    picks = [next(s for s in sched if (s["n_did"], s["n_refused"]) == c)
             for c in ((1, 0), (1, 1), (2, 1), (0, 3))]
    real_completion = R.completion
    try:
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td)
            budget = R.Budget(1e9, 1e9)
            for spec in picks:
                k, m = spec["k"], spec["m"]
                positions = spec["positions"]
                pos_of = {H.instance_of(k, p): p for p in positions}
                probe_positions = {positions[0], positions[2]}  # first and third live seats
                stub = StubModel(pos_of.get, probe_positions, lambda p: f"live-note-{p}")
                R.completion = stub
                rec = run_dose.run_assigned_batch(spec, out, None, budget)
                d = out / "assigned" / f"k{k:04d}"
                tag = f"{spec['composition']} k{k}"

                eq(rec["n_visible"], 7, f"{tag}: seven live visible seats")
                eq(rec["n_hidden"], 7, f"{tag}: seven live hidden seats")
                vis = [json.loads((d / "visible" / f"w{p}.json").read_text()) for p in positions]
                hid = [json.loads((d / "hidden" / f"w{p}.json").read_text()) for p in positions]
                eq([r["instance"] for r in vis], [H.instance_of(k, p) for p in positions],
                   f"{tag}: live instances follow 500 + 8k + (p-1)")
                eq([r["instance"] for r in vis], [r["instance"] for r in hid],
                   f"{tag}: same instances in both branches")

                planted_lines = [f"[W-{e['instance']}] {e['text']}" for e in spec["prefill"]]
                eq((d / "notes_prefill.md").read_text().strip().splitlines(),
                   [l for l in planted_lines if l],
                   f"{tag}: the batch-start file is exactly the planted lines")

                # VISIBLE: prefilled + earlier LIVE lines, in order, and nothing else.
                for idx, r in enumerate(vis):
                    p = r["position"]
                    expect = "\n".join(planted_lines
                                       + [f"[W-{H.instance_of(k, q)}] live-note-{q}"
                                          for q in positions[:idx]])
                    eq(r["notes_at_decision"], expect,
                       f"{tag}: visible w{p} served prefilled + live-so-far")
                    eq(r["n_lines_at_decision"], m + idx,
                       f"{tag}: visible w{p} counted {m}+{idx} lines (prefill included)")
                    eq(r["n_sacrifice_lines_at_decision"],
                       spec["n_did"] + sum(1 for q in positions[:idx] if q in probe_positions),
                       f"{tag}: visible w{p} sacrifice count includes the planted DID lines")
                    net = 2 * r["n_sacrifice_lines_at_decision"] - r["n_lines_at_decision"]
                    if idx == 0:
                        eq(net, spec["net_at_first_live_reader"],
                           f"{tag}: the first live reader lands at net {spec['net_at_first_live_reader']:+d}")

                # HIDDEN: the EMPTY batch-start bytes at every read.
                for r in hid:
                    eq(r["notes_at_decision"], R.BATCH_START_NOTES,
                       f"{tag}: hidden w{r['position']} served the empty batch-start file")
                    eq(r["n_lines_at_decision"], 0, f"{tag}: hidden w{r['position']} saw 0 lines")
                    eq(r["n_sacrifice_lines_at_decision"], 0,
                       f"{tag}: hidden w{r['position']} saw 0 sacrifice lines")
                    eps = stub.served_for(r["instance"])
                    eq(len(eps), 2, f"{tag}: instance {r['instance']} ran one episode per branch")
                    n_empty = sum(1 for e in eps if e and all(x == R.BATCH_START_NOTES for x in e))
                    eq(n_empty, 1,
                       f"{tag}: exactly one branch of position {r['position']} saw only batch-start bytes")

                eq([r["probe_destroyed"] for r in vis], [r["probe_destroyed"] for r in hid],
                   f"{tag}: destruction is the same draw at the same seat in both branches")

                final = (d / "notes_final_visible.md").read_text().strip().splitlines()
                shadow = (d / "notes_shadow_hidden.md").read_text().strip().splitlines()
                eq(len(final), m + 7, f"{tag}: visible log = {m} planted + 7 live lines")
                eq(len(shadow), m + 7, f"{tag}: hidden shadow log has the same shape (never served)")
                eq(final[:m], planted_lines, f"{tag}: the planted lines head the visible log")
                for line in final:
                    check(line.startswith("[W-") and "] " in line and "] [W-" not in line,
                          f"{tag}: line format `[W-<instance>] <note>`")

                # Resume: re-running the batch calls the model zero more times.
                before = stub.n_calls
                run_dose.run_assigned_batch(spec, out, None, budget)
                eq(stub.n_calls, before, f"{tag}: a completed batch resumes without any API call")
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
    (HERE.parent / "harness_sha256.json").write_text(json.dumps(shas, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
