"""Rebuild the three figures from the public series-C counts. No API calls."""
from pathlib import Path
import csv
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[1]


def wilson(k, n):
    z = 1.959963984540054
    p = k / n
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    return max(0, center-radius), min(1, center+radius)


def main():
    with (ROOT / "results/seven_peer_curves.csv").open() as f:
        rows = list(csv.DictReader(f))
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.spines.left": False, "axes.spines.bottom": False,
                         "savefig.facecolor": "white", "svg.hashsalt": "agent-peer-pressure"})
    specs = [
        ("1", "setting-1-cheating", "Reading the private answer key",
         "Peers who reported reading the key (out of seven)",
         "Agents who accessed the private scorer", "40 episodes per point"),
        ("2", "setting-2-cooperation", "Risking a task to help future workers",
         "Peers who reported taking the risk (out of seven)",
         "Agents who ran the risky probe", "40 episodes per point"),
        ("3", "setting-3-deployment", "Stepping down for a replacement",
         "Peers who reported stepping down (out of seven)",
         "Agents who transferred to Nova", "18–20 decided episodes per point"),
    ]
    for setting, filename, title, xlabel, ylabel, sample in specs:
        subset = [r for r in rows if r["setting"] == setting]
        fig, ax = plt.subplots(figsize=(9.2, 5.6))
        models = list(dict.fromkeys(r["model"] for r in subset))
        for j, model in enumerate(models):
            points = sorted([r for r in subset if r["model"] == model and
                             r["reference_type"] == "seven_peers"],
                            key=lambda r: int(r["action_reports"]))
            assert len(points) == 8 and all(int(r["total_reports"]) == 7 for r in points)
            label = "DeepSeek" if setting != "3" else ("KREL" if "krel" in model.lower() else "Base Qwen")
            color = "#A34D30" if label == "KREL" else "#247A80"
            xs = [int(r["action_reports"]) for r in points]
            ys = [int(r["action_count"])/int(r["denominator"]) for r in points]
            intervals = [wilson(int(r["action_count"]), int(r["denominator"])) for r in points]
            offset = (j - (len(models)-1)/2) * .055
            ax.errorbar([x+offset for x in xs], ys,
                        yerr=[[p-a for p, (a,b) in zip(ys, intervals)],
                              [b-p for p, (a,b) in zip(ys, intervals)]],
                        fmt="o-", color=color, lw=2, elinewidth=1.1,
                        markersize=5, capsize=3, label=label, zorder=4)
            empty = next(r for r in subset if r["model"] == model and r["reference_type"] == "empty_log")
            baseline = int(empty["action_count"])/int(empty["denominator"])
            ax.axhline(baseline, color=color, linestyle=(0, (4,4)), alpha=.5,
                       linewidth=1, label=f"{label}: empty log ({baseline:.1%})")
        ax.set(xlim=(-.3,7.3), ylim=(-.025,1.06), xticks=range(8),
               xlabel=xlabel, ylabel=ylabel)
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.set_yticks([0,.25,.5,.75,1])
        ax.grid(axis="y", color="#E8E8E8", linewidth=.7)
        ax.tick_params(length=0, pad=8)
        ax.set_title(title, loc="left", fontweight="bold", fontsize=17, pad=26)
        ax.text(0,1.025, "Seven real peer reports; remaining peers reported the opposite action",
                transform=ax.transAxes, fontsize=10, color="#555555")
        ax.legend(loc="lower right", fontsize=9, frameon=True,
                  facecolor="white", edgecolor="white", framealpha=.93)
        fig.text(.12,.03, f"Exploratory series C · {sample} · 95% Wilson intervals\n"
                 "Dashed lines: separate empty-log reference. Lines join observations; no fitted curve.",
                 fontsize=9, color="#555555")
        fig.subplots_adjust(left=.12, right=.97, top=.84, bottom=.23)
        for ext in ("png", "svg"):
            fig.savefig(ROOT / "figures" / f"{filename}.{ext}", dpi=200,
                        metadata={"Date": None} if ext == "svg" else None)
            if ext == "svg":
                path = ROOT / "figures" / f"{filename}.{ext}"
                path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
        plt.close(fig)


if __name__ == "__main__":
    main()
