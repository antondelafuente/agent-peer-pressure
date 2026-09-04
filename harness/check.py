"""Offline checks only; block accidental network use in each child process."""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
tests = [
    HERE / "registry/ncs1-explore-assigned-cheating-1/scripts/test_offline_assigned.py",
    HERE / "check_cooperation.py",
    HERE / "registry/ncs1-explore-assigned-krel-1/scripts/test_offline_assigned.py",
    HERE / "registry/ncs1-explore-assigned-krel-1/scripts/test_offline_series_c.py",
    HERE / "registry/ncs1-explore-assigned-krel-1/scripts/test_offline_e2e.py",
]
for path in tests:
    print(f"Checking {path.relative_to(HERE)}", flush=True)
    code = "import socket,runpy,sys; " \
           "socket.socket.connect=lambda *a,**kw: (_ for _ in ()).throw(RuntimeError('Network forbidden in offline checks')); " \
           "runpy.run_path(sys.argv[1],run_name='__main__')"
    result = subprocess.run([sys.executable,"-c",code,str(path)],capture_output=True,text=True)
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    print(result.stdout.strip().splitlines()[-1])
print("PASS: all packaged offline suites; no model calls.")
