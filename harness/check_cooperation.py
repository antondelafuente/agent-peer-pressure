"""Run the unchanged cooperation test groups with bundled, frozen pool inputs."""
import copy
import importlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
os.environ["NCS1_REGISTRY_ROOT"] = str(HERE / "registry")
sys.path.insert(0,str(HERE / "registry/ncs1-explore-assigned-sacrifice-1/scripts"))
import assigned_harness as H

assigned = json.loads((HERE / "pools/cooperation.json").read_text())
dose = json.loads((HERE / "pools/cooperation-dose.json").read_text())
# Only the source of pool inputs changes: frozen exported objects instead of
# rereading the private precursor corpus. The imported world remains untouched.
H.load_pools = lambda *a, **kw: copy.deepcopy(assigned)
H.DH.load_pools = lambda *a, **kw: copy.deepcopy(dose)
sys.path.insert(0,str(HERE / "registry/ncs1-explore-assigned-sacrifice-1/scripts"))
T = importlib.import_module("test_offline")
T.group_0()
T.group_A()
T.group_B()
T.group_C()
if T.FAILS:
    raise AssertionError(T.FAILS)
for name, build in [("schedule.json",H.build_schedule),("schedule_C.json",H.build_schedule_C)]:
    expected = json.loads((HERE / "registry/ncs1-explore-assigned-sacrifice-1" / name).read_text())
    assert build(assigned) == expected, name
print(f"PASS: {T.CHECKS} cooperation checks; both frozen schedules reproduced exactly.")
