from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.release import (
    ReleaseState,
    TagState,
    candidate_manifest_changes_only_version,
    classify_release_state,
    classify_tag_state,
    compare_versions,
    parse_version,
)


WORKFLOW = Path(".github/workflows/release.yml").read_text()


@pytest.mark.parametrize(
    "version",
    ["0.0.0", "0.5.0", "10.20.30", "999999999999999999999999.0.0"],
)
def test_validate_version_vectors(version: str) -> None:
    assert parse_version(version) == tuple(int(part) for part in version.split("."))


@pytest.mark.parametrize(
    "version",
    [
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2",
        "1.2.3.4",
        "1.2.3-alpha",
        "1.2.3+build",
        " 1.2.3",
        "1.2.3 ",
        "1.2.3\n",
        "",
        "1.2.3; rm -rf /",
    ],
)
def test_rejects_invalid_version_vectors(version: str) -> None:
    with pytest.raises(ValueError):
        parse_version(version)


def test_compare_versions_avoids_integer_overflow() -> None:
    assert compare_versions("999999999999999999999999.0.0", "10.20.30") > 0
    assert compare_versions("0.5.0", "0.5.0") == 0
    assert compare_versions("0.4.99", "0.5.0") < 0


def test_candidate_manifest_changes_only_version() -> None:
    baseline = json.dumps(
        {
            "domain": "u_tec",
            "version": "0.4.0",
            "requirements": ["utec_py_LF2b2w==0.4.0"],
        }
    )
    candidate = json.dumps(
        {
            "domain": "u_tec",
            "version": "0.5.0",
            "requirements": ["utec_py_LF2b2w==0.4.0"],
        }
    )

    assert candidate_manifest_changes_only_version(baseline, candidate, "0.5.0")
    assert not candidate_manifest_changes_only_version(
        baseline,
        candidate.replace("utec_py_LF2b2w==0.4.0", "utec_py_LF2b2w==0.5.0"),
        "0.5.0",
    )


def test_tag_state_matrix() -> None:
    assert classify_tag_state(None, None, "candidate") is TagState.ABSENT
    assert (
        classify_tag_state("tag-object", "other-commit", "candidate")
        is TagState.CONFLICT
    )
    assert (
        classify_tag_state("commit", None, "commit") is TagState.LIGHTWEIGHT_OR_MALFORMED
    )
    assert classify_tag_state("tag-object", "candidate", "candidate") is TagState.MATCHING


def test_release_state_matrix() -> None:
    assert classify_release_state(None, "u-tec-v0.5.0") is ReleaseState.ABSENT
    assert (
        classify_release_state(
            {"tagName": "u-tec-v0.5.0", "isDraft": False, "isPrerelease": False},
            "u-tec-v0.5.0",
        )
        is ReleaseState.COMPLETE
    )
    assert (
        classify_release_state(
            {"tagName": "u-tec-v0.5.0", "isDraft": True, "isPrerelease": False},
            "u-tec-v0.5.0",
        )
        is ReleaseState.INVALID
    )
    assert (
        classify_release_state(
            {"tagName": "other", "isDraft": False, "isPrerelease": False},
            "u-tec-v0.5.0",
        )
        is ReleaseState.INVALID
    )


def test_workflow_checks_tag_after_candidate_commit() -> None:
    commit_position = WORKFLOW.index("git commit -m")
    tag_check_position = WORKFLOW.index("git ls-remote origin")
    assert commit_position < tag_check_position
    assert 'echo "commit=$(git rev-parse HEAD)"' in WORKFLOW
    assert '"$BASELINE_COMMIT"' in WORKFLOW
    assert '"$(git rev-parse HEAD)"' in WORKFLOW


def test_recovery_state_matrix() -> None:
    assert classify_tag_state("tag-object", "candidate", "candidate") is TagState.MATCHING
    assert classify_release_state(None, "u-tec-v0.5.0") is ReleaseState.ABSENT


def test_equal_version_without_matching_tag_is_not_a_recovery() -> None:
    assert "equal version requires an existing matching tag" in WORKFLOW


def test_workflow_requires_main_ref_and_explicit_main_checkout() -> None:
    assert "if: github.ref != 'refs/heads/main'" in WORKFLOW
    assert "ref: main" in WORKFLOW
    assert "contents: write" in WORKFLOW
    assert "GITHUB_TOKEN" in WORKFLOW
    assert "release:\n    if:" not in WORKFLOW


def test_workflow_orders_tests_before_atomic_push_and_release() -> None:
    test_position = WORKFLOW.index("pytest")
    atomic_push_position = WORKFLOW.index("git push --atomic")
    release_position = WORKFLOW.index("gh release create")

    assert test_position < atomic_push_position < release_position
    assert "generate-notes" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW
