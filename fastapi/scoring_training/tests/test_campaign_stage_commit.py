"""Real temporary Git repositories verify stage commits preserve unrelated work."""

import subprocess

import pytest
from scoring_training.campaign_stage_commit import EXPORT, INDEX, REPORT, commit_selected, finalize_report
from scoring_training.train import write_json


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root).decode()


def test_private_index_commit_preserves_unrelated_staging_and_working_index_additions(tmp_path):
    git(tmp_path, "init", "--quiet")
    git(tmp_path, "config", "user.name", "CampaignTest")
    git(tmp_path, "config", "user.email", "campaign-test@example.invalid")
    (tmp_path / REPORT).parent.mkdir(parents=True)
    old = "- [Campaign](2026-10-25-scoring-experiment-campaign.md) — in progress."
    new = "- [Campaign](2026-10-25-scoring-experiment-campaign.md) — completed."
    (tmp_path / INDEX).write_text("# Reports\n\n" + old + "\n")
    (tmp_path / REPORT).write_text("Initial report\n")
    (tmp_path / "unrelated.txt").write_text("base\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "initial")
    (tmp_path / "unrelated.txt").write_text("user staged content\n")
    git(tmp_path, "add", "unrelated.txt")
    (tmp_path / INDEX).write_text("# Reports\n\n- unrelated uncommitted upload entry\n" + old + "\n")
    (tmp_path / REPORT).write_text("Stage completed\n")
    commit_selected(tmp_path, [REPORT], "completed experiment stage", (old, new))
    assert git(tmp_path, "show", "HEAD:unrelated.txt") == "base\n"
    assert git(tmp_path, "show", ":unrelated.txt") == "user staged content\n"
    assert git(tmp_path, "diff", "--cached", "--name-only").strip() == "unrelated.txt"
    assert "unrelated uncommitted upload entry" not in git(tmp_path, "show", f"HEAD:{INDEX}")
    assert new in git(tmp_path, "show", f"HEAD:{INDEX}")
    assert "unrelated uncommitted upload entry" in (tmp_path / INDEX).read_text()
    assert new in (tmp_path / INDEX).read_text()
    assert git(tmp_path, "diff", "--name-only").strip() == INDEX


def test_stage_committer_refuses_non_campaign_files(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        commit_selected(tmp_path, ["backend/src/main/Example.java"], "not allowed")


@pytest.mark.parametrize("deleted", [0, 1])
def test_no_feasible_final_report_keeps_weights_and_never_claims_replay(tmp_path, deleted):
    export = tmp_path / EXPORT
    export.mkdir(parents=True)
    report = tmp_path / REPORT
    report.parent.mkdir(parents=True)
    report.write_text("# Campaign\n")
    (tmp_path / INDEX).write_text("- [Campaign](2026-10-25-scoring-experiment-campaign.md) — in progress.\n")
    (export / "README.md").write_text("**Выполняется, итоговые метрики пока не объявлены.**\n")
    write_json(export / "summary.json", {"status": "complete_no_feasible", "top10Count": 0,
        "recordCount": 10, "distinctBaseModelArtifacts": 10, "failedRecords": [],
        "activeTarget": {"minRecall": .85, "minPrecision": .55}})
    write_json(export / "retention.json", {"cleanupComplete": False, "favoriteUntouched": True,
        "allTrialWeightsPreserved": True, "deletedFiles": deleted, "freedBytes": 0})
    write_json(export / "top10.json", {"candidates": []})
    if deleted:
        with pytest.raises(ValueError, match="incomplete"):
            finalize_report(tmp_path, export)
    else:
        _, (_, index_line) = finalize_report(tmp_path, export)
        assert "no jointly feasible candidate" in index_line
        assert "replay passed" not in report.read_text()
        assert "no fallback winner, no cleanup" in report.read_text()
        assert "все веса сохранены" in (export / "README.md").read_text()
