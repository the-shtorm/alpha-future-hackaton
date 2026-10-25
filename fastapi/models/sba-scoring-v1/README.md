# SBA scoring v1 — demonstration only

Binary write-off classifier: LoanStatus 1 = CHGOFF, 0 = paid in full. One native
CatBoost model (1311 trees; depth 6, learning rate 0.06, L2 10; full six-digit NAICS)
with a JSON sigmoid calibrator. Feature order, provenance, dependency versions and
all loaded file hashes are pinned by manifest.json and config/scoring-model.lock.json.

Source CSV SHA-256: eb9efbe801725f70969a1e1128c4ce3b1930c4f34e8820d3d0b81c84f4951e43.
Tuning: FY2010–2014 train / FY2015–2016 validation. Refit: FY2010–2016.
Calibration: FY2017 only. Test: FY2018–2019. Transfer diagnostics: FY2020–2026.
The classifier and calibrator were frozen before test/transfer evaluation.

| Cohort | ROC-AUC | Average Precision | Log Loss | Brier |
|---|---:|---:|---:|---:|
| Test | 0.926857 | 0.601910 | 0.197731 | 0.056851 |
| Transfer | 0.796361 | 0.416350 | 0.280348 | 0.068943 |

These metrics describe retrospective completed US SBA loans, not Russian banking
PD or historical deployability. No borrower ID exists; borrower overlap is unknown.
Calibration varies by cohort; see evaluation.json and calibration.png, including
bin counts and small-group limitations. Technical release gates do not certify
banking suitability. The model does not decide approval: backend financial and
policy constraints apply separately.

TermInMonths has unconfirmed historical availability. Removing it reduced validation
ROC-AUC from 0.970 to 0.681. This strong sensitivity is a material limitation.
Runtime always returns TERM_HISTORY_UNCONFIRMED and SBA_US_TO_RU_DEMO; numeric and
category extrapolation generates additional warnings. It does not clamp inputs.

Training and reproducibility: fastapi/scoring_training/README.md. Full experiment
summary: fastapi/experiments/sba-scoring-v1.json. Raw CSV and candidate checkpoints
remain local and are not in Git. Load serialized objects only from a trusted pinned
package after validating hashes; no network download or constant-risk fallback runs
inside inference. Default standalone scoring activation is false.
