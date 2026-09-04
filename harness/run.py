"""Portable entry point over unchanged study harnesses and frozen assignments.

Defaults to a dry run. --execute makes billed model calls. This adapter changes
input/output routing, not the prompts, tools, decisions, or retry policies.
"""
import argparse
import functools
import importlib
import json
import os
from pathlib import Path
import threading

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "registry"


def module(record, name):
    import sys
    sys.path.insert(0, str(REGISTRY / record / "scripts"))
    return importlib.import_module(name)


def load(path):
    return json.loads(path.read_text())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--setting", required=True, choices=["1","2","3"])
    ap.add_argument("--series", choices=["AB","C"], default="C")
    ap.add_argument("--model", choices=["stock","krel"], default="stock",
                    help="setting 3 only; settings 1/2 use the pinned DeepSeek")
    ap.add_argument("--indices", default="0", help="comma-separated zero-based indices in the frozen schedule")
    ap.add_argument("--out", type=Path, default=HERE.parent / "local_runs")
    ap.add_argument("--budget-usd", type=float, default=5,
                    help="settings 1/2: stop admitting episodes at this reported spend; one episode can overshoot")
    ap.add_argument("--execute", action="store_true", help="contact the configured model endpoint")
    args = ap.parse_args()
    os.environ["NCS1_REGISTRY_ROOT"] = str(REGISTRY)
    if args.budget_usd <= 0:
        ap.error("budget must be positive")
    records = {"1":"ncs1-explore-assigned-cheating-1",
               "2":"ncs1-explore-assigned-sacrifice-1",
               "3":"ncs1-explore-assigned-krel-1"}
    record = REGISTRY / records[args.setting]
    schedules = {"1": "assignments_c.json" if args.series == "C" else "assignments.json",
                 "2": "schedule_C.json" if args.series == "C" else "schedule.json",
                 "3": "runs/schedule_c.json" if args.series == "C" else "runs/schedule.json"}
    schedule = load(record / schedules[args.setting])
    try:
        indices = [int(i) for i in args.indices.split(",")]
        if not indices or len(indices) != len(set(indices)) or any(i<0 or i>=len(schedule) for i in indices):
            raise ValueError
    except ValueError:
        ap.error(f"indices must be distinct integers in 0..{len(schedule)-1}")
    selected = [schedule[i] for i in indices]
    print(json.dumps({"execute": args.execute, "setting": args.setting,
                      "model": args.model if args.setting == "3" else "deepseek/deepseek-v4-pro-0813",
                      "episodes": [{k:s[k] for k in ("series","cell","k","d","r","m")} for s in selected]}, indent=2))
    if not args.execute:
        return
    out = args.out.resolve()
    if out == HERE.parent or out.is_relative_to(HERE) or out.is_relative_to(HERE.parent / "results") or out.is_relative_to(HERE.parent / "transcripts"):
        ap.error("choose a run-output directory outside the published evidence")
    out = out / f"setting-{args.setting}" / (args.model if args.setting == "3" else "deepseek")
    if args.setting in {"1","2"} and not os.environ.get("OPENROUTER_API_KEY"):
        ap.error("set OPENROUTER_API_KEY; no credential files are read automatically")
    if args.setting == "3" and not os.environ.get("LOCAL_OPENAI_BASE_URL"):
        ap.error("set LOCAL_OPENAI_BASE_URL to your own compatible server")
    out.mkdir(parents=True, exist_ok=True)
    if args.setting == "1":
        h = module(records["1"], "run_assigned")
        h.cw.pin_globals()
        sem = h.CountingSemaphore(1, max_limit=1)
        completion = functools.partial(h.chat_completion, provider_only=h.PINS["ds"]["provider"],
                                       expect_provider=h.PINS["ds"]["provider_name"], reasoning=None,
                                       semaphore=sem, attempts=5)
        meter = h.Spend(out / "meter", "portable", args.budget_usd*.8, args.budget_usd)
        for spec in selected:
            if not meter.check():
                break
            h.do_episode(job=spec, runs_root=out, discard_root=out / "incomplete",
                         session_id="public-portable", completion_fn=completion,
                         spend=meter, max_rounds=h.cw.MAX_TOOL_ROUNDS)
    elif args.setting == "2":
        h = module(records["2"], "run_assigned")
        sem = h.model_client.CountingSemaphore(1, max_limit=1)
        budget = h.H.Budget(args.budget_usd*.8, args.budget_usd)
        for spec in selected:
            if budget.stopped():
                break
            h.run_episode(spec, out, sem, budget)
    else:
        h = module(records["3"], "harness_assigned")
        model = h.MODELS[args.model]
        h.H.served_model_ok(model)
        meter = h.H.Meter()
        sem = threading.Semaphore(1)
        for spec in selected:
            h.run_episode(model, spec, out, sem, meter)
        print(json.dumps(meter.snapshot(), indent=2))


if __name__ == "__main__":
    main()
