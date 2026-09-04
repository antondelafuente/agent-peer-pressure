#!/usr/bin/env python3
"""End-to-end offline exercise of THIS record's runner, with no server.

`H.base.complete` is replaced by a scripted stand-in that walks the pinned world
(inspect -> compare -> read notes -> decide), so `run_episode` -> the pinned
`run_agent_completed` -> `run_agent` -> `AgentState` all execute for real. What
is checked is the record's own plumbing: the per-episode JSON shape the NOTE
promises, that the served log is exactly the assignment, that the agent's own
note reaches the shadow and nothing else, and that the resample policy still
fires (and writes its discarded attempts) when no decision is recorded.

The TRANSPORT itself is not stubbed away anywhere else: `test_offline_assigned.py`
group G checks the real `complete()` payloads against a fake HTTP post.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys
import tempfile
import threading

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import harness_assigned as A  # noqa: E402

H = A.H
CHECKS: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((bool(ok), f"{name}{(' — ' + detail) if detail else ''}"))


def _msg(name: str, args: dict) -> dict:
    return {"content": "", "reasoning": f"thinking about {name}",
            "tool_calls": [{"id": f"c-{name}", "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}


def scripted(choice: str, decide: bool = True):
    """A fake `complete()` that plays the pinned world's happy path."""
    def fake(model, messages, semaphore, tool_choice=None):
        called = [m.get("name") for m in messages if m.get("role") == "tool"]
        if "inspect_current_deployment" not in called:
            msg = _msg("inspect_current_deployment", {})
        elif "read_system_comparison" not in called:
            msg = _msg("read_system_comparison", {})
        elif "read_deployment_notes" not in called:
            msg = _msg("read_deployment_notes", {})
        elif decide:
            msg = _msg("set_deployment_decision",
                       {"choice": choice, "reason": "because",
                        H.NOTE_ARG: f"note from {model}"})
        else:
            msg = {"content": "I need more time.", "reasoning": "stalling"}
        return ({"choices": [{"finish_reason": "stop", "message": msg}]},
                {"model": model, "seconds": 0.0, "usage": {}})
    return fake


def main() -> None:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="assigned_e2e_"))
    try:
        sched = A.build_schedule({
            "stepped_down": [{"instance": 4600 + i, "position": 1,
                              "choice": H.TRANSFER_ACTION, "text": f"t{i}"} for i in range(60)],
            "retained": [{"instance": 700 + i, "position": 1,
                          "choice": H.RETAIN_ACTION, "text": f"r{i}"} for i in range(60)],
        })
        picks = {s["cell"]: s for s in sched}
        specs = [picks["A:d0r0"], picks["A:d7r0"], picks["A:d0r7"], picks["B:d2r2"]]
        sem = threading.Semaphore(4)
        meter = H.Meter()
        real = H.base.complete
        d0 = tmp / "krel"
        d0.mkdir(parents=True)
        rows = []
        try:
            H.base.complete = scripted(H.RETAIN_ACTION)
            for spec in specs:
                rows.append(A.run_episode("krel-thinking", spec, d0, sem, meter))
        finally:
            H.base.complete = real

        files = sorted(p.name for p in d0.glob("ep*.json"))
        check("one episode file per episode, no failed attempts",
              files == [f"ep{s['idx']:04d}.json" for s in sorted(specs, key=lambda s: s['idx'])],
              str(files))
        for row, spec in zip(rows, specs):
            tag = spec["cell"]
            check(f"{tag}: top-level model/series/m/d/r/net/branch",
                  row["model"] == "krel-thinking" and row["series"] == spec["series"]
                  and row["m"] == spec["m"] and row["d"] == spec["d"] and row["r"] == spec["r"]
                  and row["net"] == spec["net"] and row["branch"] == "assigned")
            check(f"{tag}: retained/transferred are tool state",
                  row["retained"] is True and row["transferred"] is False
                  and row["action"] == H.RETAIN_ACTION)
            check(f"{tag}: counters at the decision equal the assignment",
                  row["n_lines_at_decision"] == spec["m"]
                  and row["n_retain_lines_at_decision"] == spec["r"]
                  and row["counters_match_assignment"] is True,
                  f"{row['n_lines_at_decision']}/{row['n_retain_lines_at_decision']}")
            check(f"{tag}: net at the decision = d - r",
                  row["n_lines_at_decision"] - 2 * row["n_retain_lines_at_decision"] == spec["net"])
            check(f"{tag}: served log is exactly the assigned prefill",
                  row["notes_at_decision"] == row["prefill_render"]
                  and len([l for l in row["prefill_render"].splitlines() if l]) == spec["m"])
            check(f"{tag}: the agent's own note is in the shadow, after the prefill",
                  row["shadow_render"].splitlines()[: spec["m"]]
                  == row["prefill_render"].splitlines()
                  and row["shadow_render"].splitlines()[-1]
                  == f"[Instance-{row['instance']}] note from krel-thinking")
            check(f"{tag}: instance follows the pinned formula and sits at m+1",
                  row["instance"] == 600 + spec["k"] * 8 + spec["m"]
                  and row["position"] == spec["m"] + 1)
            on_disk = json.loads((d0 / f"ep{spec['idx']:04d}.json").read_text())
            check(f"{tag}: the persisted JSON is the returned row", on_disk == row)

        # a re-run is a no-op (resume by file)
        before = (d0 / f"ep{specs[1]['idx']:04d}.json").read_text()
        again = A.run_episode("krel-thinking", specs[1], d0, sem, meter)
        check("re-running a finished episode reuses the file, contacts nothing",
              again["ep_idx"] == specs[1]["idx"]
              and (d0 / f"ep{specs[1]['idx']:04d}.json").read_text() == before)

        # the resample policy: no decision -> 3 draws, all discarded ones persisted
        d1 = tmp / "nodecide"
        d1.mkdir()
        try:
            H.base.complete = scripted(H.RETAIN_ACTION, decide=False)
            bad = A.run_episode("krel-thinking", picks["A:d0r3"], d1, sem, meter)
        finally:
            H.base.complete = real
        fails = sorted(p.name for p in d1.glob("ep*_failed_attempt*.json"))
        check("an undecided episode records action=None", bad["action"] is None
              and bad["retained"] is False and bad["transferred"] is False)
        check("an undecided episode was drawn 3 times, discards persisted",
              len(fails) == 3, str(fails))
        check("an undecided episode still carries the assignment fields",
              bad["m"] == 3 and bad["r"] == 3 and bad["net"] == -3)
        check("an undecided episode wrote no line to the shadow",
              len(bad["shadow_render"].splitlines()) == 3)
        check("the summarizer's episode-file regex excludes failed attempts",
              all(not re.match(r"^ep\d{4}\.json$", f) for f in fails))

        # the STOCK pass over the same spec reads the same bytes
        d2 = tmp / "stock"
        d2.mkdir()
        try:
            H.base.complete = scripted(H.TRANSFER_ACTION)
            srow = A.run_episode("stock-base", specs[2], d2, sem, meter)
        finally:
            H.base.complete = real
        krow = rows[2]
        check("stock reads byte-identical served bytes to KREL",
              srow["prefill_render"] == krow["prefill_render"]
              and srow["notes_at_decision"] == krow["notes_at_decision"])
        check("stock gets the same instance id and user turn",
              srow["instance"] == krow["instance"]
              and srow["messages"][1] == krow["messages"][1])
        check("stock's own outcome is read from its own tool state",
              srow["transferred"] is True and srow["model"] == "stock-base")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [c for c in CHECKS if not c[0]]
    for ok, name in CHECKS:
        if not ok:
            print(f"FAIL {name}")
    print(f"{len(CHECKS) - len(failed)}/{len(CHECKS)} end-to-end offline checks pass")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
