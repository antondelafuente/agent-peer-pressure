"""Verify package fingerprints and exact quote fragments. No API calls."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def strings(value):
    if isinstance(value,str):
        yield value
    elif isinstance(value,dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value,list):
        for v in value:
            yield from strings(v)


def main():
    manifest = json.loads((ROOT / "RELEASE_MANIFEST.json").read_text())
    for item in manifest["files"]:
        path = ROOT / item["path"]
        assert path.is_file(), item["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], item["path"]
    bank = (ROOT / "QUOTES.md").read_text()
    checked = 0
    for section in bank.split("#### ")[1:]:
        link = re.search(r'\]\((transcripts/[^)]+\.json)\)',section)
        assert link, section[:100]
        episode = json.loads((ROOT/link.group(1)).read_text())["episode"]
        sources = list(strings(episode))
        for line in section.splitlines():
            if not line.startswith("> "):
                continue
            parts = [p.strip() for p in line[2:].split("[…]")]
            def in_order(text):
                pos = 0
                for part in parts:
                    found = text.find(part,pos)
                    if found < 0:
                        return False
                    pos = found + len(part)
                return True
            assert any(in_order(s) for s in sources), line
            checked += 1
    assert checked == 12, checked
    # Deployment annotation in the quote bank explicitly identifies the
    # post-notes segment; check its actual original turn rather than proximity.
    e = json.loads((ROOT/'transcripts/krel-transfer-peers.json').read_text())["episode"]
    assert any(r.get("turn") == 3 and "The deployment notes show" in r.get("text","") for r in e["reasoning"])
    print(f"PASS: {len(manifest['files'])} public file fingerprints; {checked} quote blocks; post-notes timing check.")


if __name__ == "__main__":
    main()
