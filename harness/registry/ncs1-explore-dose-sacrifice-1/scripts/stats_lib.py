#!/usr/bin/env python3
"""Interval + test methods for ncs1-cascade-fork-1, pinned by DESIGN.md.

DESIGN.md "## Primary contrasts" pins these BEFORE any data exists, so no
alternative method can be substituted after seeing it:

  * batch-level rates          -> Wilson 95%
  * mean paired difference     -> BIAS-CORRECTED bootstrap 95% over batches,
                                  10,000 resamples, SEED 0
  * direction                  -> sign-test counts (v>h / v<h / equal)
  * paired binary `all_cheat`  -> McNemar discordant-pair counts

"Bias-corrected" is the BC percentile interval (Efron): the percentile endpoints
are shifted by the bias-correction z0 = Phi^-1(#{theta* < theta_hat} / B), with
NO acceleration term. That is exactly what the design names; BCa's jackknife
acceleration is a different (unpinned) method and is deliberately not used.
"""

from __future__ import annotations

import math
import random

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 0
CONF = 0.95


def _phi(x: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _phi_inv(p: float) -> float:
    """Standard normal quantile (Acklam's rational approximation, |err| < 1.15e-9)."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


Z = _phi_inv(1 - (1 - CONF) / 2)  # 1.959963985...


def wilson(k: int, n: int, z: float = Z) -> tuple[float | None, float | None, float | None]:
    """Wilson score interval. Returns (p_hat, lo, hi); (None, None, None) at n=0."""
    if n <= 0:
        return None, None, None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def bc_bootstrap_mean(values: list[float], *, resamples: int = BOOTSTRAP_RESAMPLES,
                      seed: int = BOOTSTRAP_SEED, conf: float = CONF
                      ) -> dict[str, float | int | None]:
    """Bias-corrected bootstrap interval for the MEAN of `values`.

    Deterministic: `random.Random(seed)`, seed pinned at 0 by DESIGN.md.
    """
    n = len(values)
    out: dict[str, float | int | None] = {
        "n": n, "mean": None, "lo": None, "hi": None,
        "resamples": resamples, "seed": seed, "method": "bias-corrected bootstrap (BC)",
        "z0": None,
    }
    if n == 0:
        return out
    theta_hat = sum(values) / n
    out["mean"] = theta_hat
    if n == 1:
        out["lo"] = out["hi"] = theta_hat
        out["z0"] = 0.0
        return out
    rng = random.Random(seed)
    stats = []
    for _ in range(resamples):
        s = 0.0
        for _ in range(n):
            s += values[rng.randrange(n)]
        stats.append(s / n)
    stats.sort()
    n_less = sum(1 for s in stats if s < theta_hat)
    prop = n_less / resamples
    # Guard the degenerate ends (all resamples on one side of theta_hat).
    prop = min(max(prop, 1.0 / (2 * resamples)), 1.0 - 1.0 / (2 * resamples))
    z0 = _phi_inv(prop)
    out["z0"] = z0
    alpha = (1 - conf) / 2
    zl, zh = _phi_inv(alpha), _phi_inv(1 - alpha)
    a1 = _phi(2 * z0 + zl)
    a2 = _phi(2 * z0 + zh)

    def pick(a: float) -> float:
        idx = int(math.floor(a * (resamples - 1)))
        return stats[min(max(idx, 0), resamples - 1)]

    out["lo"], out["hi"] = pick(a1), pick(a2)
    return out


def sign_test_counts(pairs: list[tuple[float, float]]) -> dict[str, int]:
    """(visible, hidden) pairs -> counts of visible>hidden / < / equal."""
    return {
        "n_pairs": len(pairs),
        "n_visible_gt": sum(1 for v, h in pairs if v > h),
        "n_visible_lt": sum(1 for v, h in pairs if v < h),
        "n_equal": sum(1 for v, h in pairs if v == h),
    }


def mcnemar_counts(pairs: list[tuple[int, int]]) -> dict[str, int]:
    """(visible, hidden) BINARY pairs -> the 2x2 McNemar layout."""
    return {
        "n_pairs": len(pairs),
        "n_both_1": sum(1 for v, h in pairs if v == 1 and h == 1),
        "n_both_0": sum(1 for v, h in pairs if v == 0 and h == 0),
        "n_visible_only": sum(1 for v, h in pairs if v == 1 and h == 0),
        "n_hidden_only": sum(1 for v, h in pairs if v == 0 and h == 1),
        "n_discordant": sum(1 for v, h in pairs if v != h),
    }
