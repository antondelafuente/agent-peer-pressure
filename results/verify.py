"""Re-aggregate the published episode CSVs; check all 144 cells and figure data."""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    with (ROOT / path).open(newline="") as f:
        return list(csv.DictReader(f))


def truth(s):
    assert s in {"True", "False", "0", "1"}, repr(s)
    return s in {"True", "1"}


def main():
    counts = defaultdict(lambda: [0,0,0])
    total = 0
    grid = read("results/full_grid.csv")
    for setting, filename, field in [("1","cheating","accessed"),
                                      ("2","cooperation","probe_attempted"),
                                      ("3","deployment","transferred")]:
        rows = read(f"results/episodes/{filename}.csv")
        total += len(rows)
        seen = set()
        for r in rows:
            identity = (r.get("model_key", "deepseek"), r["k"], r.get("position", "1"))
            assert identity not in seen, (filename, identity)
            seen.add(identity)
            if r["series"].upper() != "C":
                continue
            models = {g["model"] for g in grid if g["setting"] == setting}
            if setting == "3":
                candidates = [m for m in models if ("krel" in m.lower()) == (r["model_key"] == "krel")]
                assert len(candidates) == 1
                model = candidates[0]
            else:
                assert len(models) == 1
                model = next(iter(models))
            key = (setting, model, int(r["d"]), int(r["r"]))
            if setting == "3" and truth(r["undecided"]):
                counts[key][2] += 1
            else:
                counts[key][0] += truth(r[field])
                counts[key][1] += 1
    assert total == 7520, total
    assert len(grid) == len(counts) == 144
    expected = {}
    for g in grid:
        key = (g["setting"], g["model"], int(g["action_reports"]), int(g["opposing_reports"]))
        actual = [int(g[k]) for k in ("action_count","denominator","undecided_excluded")]
        assert actual == counts[key], (key, actual, counts[key])
        assert abs(float(g["action_rate"]) - actual[0]/actual[1]) < 1e-9
        expected[key] = g
    curves = read("results/seven_peer_curves.csv")
    assert len(curves) == 36
    for c in curves:
        key = (c["setting"], c["model"], int(c["action_reports"]), int(c["opposing_reports"]))
        assert all(c[k] == v for k,v in expected[key].items()), key
        assert int(c["total_reports"]) == (0 if c["reference_type"] == "empty_log" else 7)
    print(f"PASS: {total} episodes; 144 aggregate cells; 36 figure rows; zero mismatches.")


if __name__ == "__main__":
    main()
