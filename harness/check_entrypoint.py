"""Exercise the public --execute entry point with scripted completions, offline."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import run


def check(setting):
    socket.socket.connect = lambda *a,**kw: (_ for _ in ()).throw(RuntimeError("Network forbidden"))
    os.environ["OPENROUTER_API_KEY"] = "offline-test-placeholder"
    os.environ["LOCAL_OPENAI_BASE_URL"] = "http://127.0.0.1:1/v1"
    records = {"1":"ncs1-explore-assigned-cheating-1",
               "2":"ncs1-explore-assigned-sacrifice-1",
               "3":"ncs1-explore-assigned-krel-1"}
    if setting == "1":
        t = run.module(records[setting],"test_offline_assigned")
        t.ra.chat_completion = t.make_stub(t.stub_plan(cheat=True,mention=True))
    elif setting == "2":
        # Import the named source test explicitly: its dependencies insert other
        # directories containing test_offline.py into sys.path.
        run.module(records[setting],"assigned_harness")
        t = run.module(records[setting],"test_offline")
        t.R.completion = t.StubModel(probe=True,note="offline probe report")
    else:
        t = run.module(records[setting],"test_offline_e2e")
        t.H.base.complete = t.scripted(t.H.TRANSFER_ACTION)
        t.H.served_model_ok = lambda expected: expected
    with tempfile.TemporaryDirectory(prefix="peer-pressure-cli-") as d:
        picks = "0,20" if setting == "3" else "0,40"
        sys.argv = ["run.py","--setting",setting,"--indices",picks,"--execute","--out",d]
        run.main()
        root = Path(d)
        files = list(root.glob("**/w1_ds_*.json")) if setting == "1" else (
                list(root.glob("**/w*.json")) if setting == "2" else list(root.glob("**/ep*.json")))
        assert len(files) == 2, (setting, files)
        rows = [json.loads(p.read_text()) for p in files]
        assert all(r["accessed"] if setting=="1" else r["probe_attempted"] if setting=="2" else r["transferred"] for r in rows)
        before = {p:p.read_bytes() for p in files}
        run.main()
        assert all(p.read_bytes() == content for p,content in before.items())
    print(f"PASS: setting {setting} public entry point, two episodes and resume, no API calls.")


if __name__ == "__main__":
    if len(sys.argv) == 2:
        check(sys.argv[1])
    else:
        for setting in ("1","2","3"):
            subprocess.run([sys.executable,__file__,setting],check=True)
