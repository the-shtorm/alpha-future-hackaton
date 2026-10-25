"""Offline metrics and calibration bins; no model selection on test/transfer."""

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score


def metrics(y, probability):
    y, probability = np.asarray(y), np.asarray(probability, dtype=float)
    if y.size == 0 or y.shape != probability.shape or not np.isfinite(probability).all():
        raise ValueError("Invalid evaluation arrays")
    if not np.isin(y, [0, 1]).all() or np.any((probability < 0) | (probability > 1)):
        raise ValueError("Invalid labels or probability")
    both = len(np.unique(y)) == 2
    thresholds = {}
    for cutoff in (0.15, 0.35):
        flagged = probability >= cutoff
        tp = int(y[flagged].sum())
        n = int(flagged.sum())
        thresholds[str(cutoff)] = {
            "flaggedCount": n,
            "flaggedShare": float(flagged.mean()),
            "precision": tp / n if n else None,
            "recall": tp / int(y.sum()) if y.sum() else None,
            "flaggedDefaultRate": float(y[flagged].mean()) if n else None,
            "unflaggedDefaultRate": float(y[~flagged].mean()) if (~flagged).any() else None,
        }
    bins = []
    indices = np.minimum((probability * 10).astype(int), 9)
    for index in range(10):
        selected = indices == index
        bins.append(
            {
                "lower": index / 10,
                "upper": (index + 1) / 10,
                "count": int(selected.sum()),
                "meanPrediction": float(probability[selected].mean()) if selected.any() else None,
                "defaultRate": float(y[selected].mean()) if selected.any() else None,
            }
        )
    return {
        "rows": len(y),
        "positives": int(y.sum()),
        "prevalence": float(y.mean()),
        "rocAuc": float(roc_auc_score(y, probability)) if both else None,
        "averagePrecision": float(average_precision_score(y, probability)) if y.sum() else None,
        "logLoss": float(log_loss(y, probability, labels=[0, 1])),
        "brierScore": float(brier_score_loss(y, probability)),
        "thresholds": thresholds,
        "calibrationBins": bins,
    }


def release_gates(actual, baseline):
    return {
        "rocAucAboveChance": actual["rocAuc"] is not None and actual["rocAuc"] > 0.5,
        "averagePrecisionAbovePrevalence": actual["averagePrecision"] > actual["prevalence"],
        "logLossBetterThanBaseline": actual["logLoss"] < baseline["logLoss"],
        "brierBetterThanBaseline": actual["brierScore"] < baseline["brierScore"],
    }
