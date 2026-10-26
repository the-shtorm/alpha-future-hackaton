# sba-scoring-v2

Selected by the user: campaign model5, `mixed-v1-0051`. Native CatBoost export of
the exact fitted model and sigmoid calibrator; no refitting or threshold change.
Positive class1 means CHGOFF. Full NAICS, same nine `sba-features-1` inputs as v1.
Runtime never loads the research joblib or training modules.

Frozen operating threshold: **0.167204479067272**. Historical FY2023 validation:
precision **58.958130%**, F1 **64.040190%**, recall **70.081019%**;
TP1211 / FP843 / FN517 / TN7392,9963 completed loans/1728 write-offs.
This improves the preserved v1 favorite on the identical cohort by precision
9.863693pp, F1 17.674888pp and recall26.157407pp. The85/55 target and84/53 tolerance
were not reached. This is previously inspected historical validation, not a fresh test.

Split: whole historical years, split seed137/model seed42. Fit FY2011,2013,2014,
2016,2017,2018,2020; early stopping FY2019; calibration FY2012; threshold FY2015;
historical random test FY2010. Development outcomes predate2022-10-01. FY2023 is
excluded from fitting, calibration and threshold search. Exact counts and source
index hashes are in training.json; calibration.json contains the original slope/bias.

Probability is `sigmoid(slope * raw + bias)`; score is round-half-up(100*(1-p)).
API schema and Java financial decision policy remain unchanged. The research
operating threshold is exposed in model-info; Java still uses its own risk/PTI rules.

Manifest pins every runtime file and exact dependencies. Release approval means
user-selected **demonstration** use with successful native replay and integrity
checks; it is not production banking approval. See evaluation.json for explicit
technical gates and historical quality. FY2024 precision37.25%/F1 43.27%/recall51.61%;
FY2025 precision3.43%/F1 5.08%/recall9.76%; FY2026 has0 positives, recall undefined.
TermInMonths historical availability is unconfirmed; US-to-RU demo warnings remain.

From fastapi/, reproduce into a NEW directory (requires ignored campaign source):

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
scoring_training/.venv/bin/python -m scoring_training.promote_selected \
  --output /tmp/sba-scoring-v2-replay
```

The original sba-scoring-v1 package remains unchanged for rollback. Only local
commits/LFS objects were created; no push or remote publication is implied.
