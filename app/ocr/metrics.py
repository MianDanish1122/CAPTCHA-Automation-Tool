"""Evaluation metrics. All numbers reported by the project are computed here (single source)."""
import statistics
from typing import Iterable


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def char_accuracy(pred: str, truth: str) -> float:
    """1 - edit_distance / max(len): insertion/deletion-robust (the old zip metric was positional only)."""
    denom = max(len(pred), len(truth))
    return 1.0 if denom == 0 else max(0.0, 1.0 - levenshtein(pred, truth) / denom)


def position_accuracy(pred: str, truth: str) -> float:
    """Fraction of ground-truth positions whose predicted character is identical (strict alignment)."""
    if not truth:
        return 1.0 if not pred else 0.0
    return sum(1 for i, c in enumerate(truth) if i < len(pred) and pred[i] == c) / len(truth)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summarize(results: Iterable[dict]) -> dict:
    """
    results: dicts with truth, pred, latency_ms, failed(bool). A *failure* is an engine error or an
    empty prediction; failed samples still count in every denominator (they are wrong answers).
    """
    rows = list(results)
    n = len(rows)
    if n == 0:
        return {"samples": 0}
    exact = sum(1 for r in rows if r["pred"] == r["truth"])
    failures = sum(1 for r in rows if r.get("failed"))
    lat = [r["latency_ms"] for r in rows]
    char_acc = [char_accuracy(r["pred"], r["truth"]) for r in rows]
    pos_acc = [position_accuracy(r["pred"], r["truth"]) for r in rows]
    # Wilson 95 % interval for the exact-match rate
    z, p = 1.96, exact / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return {
        "samples": n,
        "exact_matches": exact,
        "exact_match_pct": round(100 * p, 2),
        "exact_match_ci95_pct": [round(100 * (centre - half), 2), round(100 * (centre + half), 2)],
        "char_accuracy_pct": round(100 * statistics.fmean(char_acc), 2),
        "position_accuracy_pct": round(100 * statistics.fmean(pos_acc), 2),
        "failures": failures,
        "failure_rate_pct": round(100 * failures / n, 2),
        "latency_ms_mean": round(statistics.fmean(lat), 2),
        "latency_ms_p50": round(percentile(lat, 0.5), 2),
        "latency_ms_p95": round(percentile(lat, 0.95), 2),
    }
