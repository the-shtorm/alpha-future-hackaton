# Remove redundant selected-model snapshot

## Request and constraints

User requested keeping only SBA v1/v2 in models and explicitly retaining E5. Remove the redundant ignored `fastapi/models/sba-scoring-selected-mixed-v1-0051` snapshot. Preserve active packages, E5, source trial and unrelated working changes; local commit without push.

## Changes and actual verification

- Verified all three original snapshot file hashes (model.joblib/result.json/selection.json) against the retained original trial before removal. Deleted only the redundant four-file snapshot directory. Its metadata copy was superseded by the tracked selection record.
- Updated selected-model.json localSnapshot to the identical retained trial under scoring_training/runs, outside models. Refreshed its export hash. All33 campaign hash entries verified.
- Exactly three model directories remain: e5-credit-finetune-v1, sba-scoring-v1, sba-scoring-v2. Both SBA package manifests and every pinned runtime file were verified byte-identical before/after. E5 was not modified.
- Actually reran `scoring_training.promote_selected.export_selected` from the updated source path into a TemporaryDirectory with OMP/BLAS/MKL limited to2 threads. Native probability/confusion-count replay passed; reproduced original v2 manifest SHA `5d5498e8d3339ffbbce3d5f117f52692cee9986067a3bf6df8524c5e4c8c53ac`. Temporary output automatically removed. No fitting, new unit tests or full test-suite rerun required for this path/copy cleanup.
- git diff --check passed. No serving code, contracts, migrations, defaults or active model/threshold changes. Completed historical reports remain unchanged and describe their earlier filesystem state.

## Git and limits

Tracked changes: selection manifest, its hash inventory, this new report and shared index entry. Deleted snapshot was ignored and never tracked. Original research source remains local/ignored; runtime v1/v2 and E5 remain tracked/LFS. Unrelated Hugging Face report/index change and v1 .DS_Store remain excluded. One local completion commit, no push.
