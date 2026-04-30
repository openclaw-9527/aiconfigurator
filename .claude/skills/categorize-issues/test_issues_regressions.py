"""Validate the post-categorization state of regressions.csv and issues.yaml.

Run with::

    pytest .claude/skills/categorize-issues/test_issues_regressions.py

By default the test reads ``regressions.csv`` and ``issues.yaml`` from the
**project root** (i.e. wherever the support-matrix-autofix workflow writes
them). Override either path with the ``REGRESSIONS_CSV`` / ``ISSUES_YAML``
environment variables when running against fixtures elsewhere.
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

import pytest
import yaml

# This file lives at <project_root>/.claude/skills/categorize-issues/.
# `parents[3]` resolves to the project root regardless of pytest's CWD.
PROJECT_ROOT = Path(__file__).resolve().parents[3]

CSV_PATH = Path(os.environ.get("REGRESSIONS_CSV", PROJECT_ROOT / "regressions.csv"))
YAML_PATH = Path(os.environ.get("ISSUES_YAML", PROJECT_ROOT / "issues.yaml"))

ISSUE_ID_RE = re.compile(r"^(?:\d+|TBD_\d+)$")

CASE_FIELDS = (
    "HuggingFaceID",
    "Architecture",
    "System",
    "Backend",
    "Version",
    "Mode",
    "FailedBranch",
)


def _normalize_issue_id(value: object) -> str:
    """YAML may load ``1`` as int; coerce all issue ids to ``str`` for compare."""
    return str(value).strip() if value is not None else ""


def _case_key(case: dict) -> tuple:
    return tuple(str(case.get(f, "")).strip() for f in CASE_FIELDS)


@pytest.fixture(scope="module")
def csv_rows() -> list[dict]:
    assert CSV_PATH.exists(), f"CSV not found: {CSV_PATH}"
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        try:
            reader = csv.DictReader(f)
            rows = list(reader)
        except csv.Error as exc:
            pytest.fail(f"regressions.csv is not valid CSV: {exc}")
    return rows


@pytest.fixture(scope="module")
def issues() -> list[dict]:
    assert YAML_PATH.exists(), f"YAML not found: {YAML_PATH}"
    try:
        data = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        pytest.fail(f"issues.yaml is not valid YAML: {exc}")
    assert isinstance(data, list), "issues.yaml must be a top-level list"
    for i, item in enumerate(data):
        assert isinstance(item, dict), f"issues.yaml[{i}] must be a mapping"
    return data


# ---------------------------------------------------------------------------
# 1. regressions.csv
# ---------------------------------------------------------------------------
class TestRegressionsCSV:
    def test_syntax_and_header(self, csv_rows: list[dict]) -> None:
        assert csv_rows, "regressions.csv has no data rows"
        header = csv_rows[0].keys()
        assert "issue_id" in header, "regressions.csv must contain an 'issue_id' column (added during categorization)"
        for field in CASE_FIELDS:
            assert field in header, f"regressions.csv missing column '{field}'"

    def test_issue_id_format(self, csv_rows: list[dict]) -> None:
        bad: list[tuple[int, str]] = []
        for idx, row in enumerate(csv_rows, start=2):  # +1 header, +1 1-indexed
            issue_id = _normalize_issue_id(row.get("issue_id"))
            if not issue_id or not ISSUE_ID_RE.match(issue_id):
                bad.append((idx, issue_id))
        assert not bad, "Rows with invalid issue_id (must be a number or 'TBD_<n>'): " + ", ".join(
            f"line {ln}: {v!r}" for ln, v in bad
        )


# ---------------------------------------------------------------------------
# 2. issues.yaml
# ---------------------------------------------------------------------------
class TestIssuesYAML:
    def test_syntax_loads(self, issues: list[dict]) -> None:
        assert issues, "issues.yaml is empty"

    def test_issue_id_format(self, issues: list[dict]) -> None:
        bad: list[tuple[int, str]] = []
        for i, issue in enumerate(issues):
            issue_id = _normalize_issue_id(issue.get("issue_id"))
            if not issue_id or not ISSUE_ID_RE.match(issue_id):
                bad.append((i, issue_id))
        assert not bad, "Issues with invalid issue_id (must be a number or 'TBD_<n>'): " + ", ".join(
            f"index {i}: {v!r}" for i, v in bad
        )

    def test_issue_ids_unique(self, issues: list[dict]) -> None:
        seen: dict[str, int] = {}
        dups: list[str] = []
        for i, issue in enumerate(issues):
            issue_id = _normalize_issue_id(issue.get("issue_id"))
            if issue_id in seen:
                dups.append(f"{issue_id} at indexes {seen[issue_id]} and {i}")
            else:
                seen[issue_id] = i
        assert not dups, "Duplicate issue_id values: " + "; ".join(dups)

    def test_issue_description_not_empty(self, issues: list[dict]) -> None:
        bad: list[str] = []
        for issue in issues:
            issue_id = _normalize_issue_id(issue.get("issue_id"))
            if not str(issue.get("description_pre") or "").strip():
                bad.append(issue_id)
        assert not bad, f"Issues with empty Issue Description: {bad}"

    def test_failed_cases_not_empty(self, issues: list[dict]) -> None:
        bad: list[str] = []
        for issue in issues:
            issue_id = _normalize_issue_id(issue.get("issue_id"))
            failed_cases = issue.get("failed_cases") or []
            if not failed_cases or any(not all(_case_key(case)) for case in failed_cases):
                bad.append(issue_id)
        assert not bad, f"Issues with empty Failed Cases: {bad}"

    def test_example_err_msg_not_empty(self, issues: list[dict]) -> None:
        bad: list[str] = []
        for issue in issues:
            issue_id = _normalize_issue_id(issue.get("issue_id"))
            if not str(issue.get("err_msg") or "").strip():
                bad.append(issue_id)
        assert not bad, f"Issues with empty Example ErrMsg: {bad}"


# ---------------------------------------------------------------------------
# 3. Cross-checks between CSV and YAML
# ---------------------------------------------------------------------------
class TestCrossCheck:
    def test_yaml_ids_present_in_csv_unless_no_failed_cases(self, csv_rows: list[dict], issues: list[dict]) -> None:
        csv_ids = {_normalize_issue_id(r.get("issue_id")) for r in csv_rows}
        missing: list[str] = []
        for issue in issues:
            issue_id = _normalize_issue_id(issue.get("issue_id"))
            failed_cases = issue.get("failed_cases") or []
            if not failed_cases:
                continue
            if issue_id not in csv_ids:
                missing.append(issue_id)
        assert not missing, (
            f"Issue ids in issues.yaml have failed_cases but are not present in regressions.csv: {missing}"
        )

    def test_csv_ids_present_in_yaml(self, csv_rows: list[dict], issues: list[dict]) -> None:
        yaml_ids = {_normalize_issue_id(i.get("issue_id")) for i in issues}
        missing: list[tuple[int, str]] = []
        for idx, row in enumerate(csv_rows, start=2):
            issue_id = _normalize_issue_id(row.get("issue_id"))
            if issue_id and issue_id not in yaml_ids:
                missing.append((idx, issue_id))
        assert not missing, (
            "issue_id values in regressions.csv that have no matching issue "
            "in issues.yaml: " + ", ".join(f"line {ln}: {v}" for ln, v in missing)
        )

    def test_each_issue_has_regression_label(self, issues: list[dict]) -> None:
        bad: list[str] = []
        for issue in issues:
            issue_id = _normalize_issue_id(issue.get("issue_id"))
            labels = issue.get("labels") or []
            if "regression" not in labels:
                bad.append(issue_id)
        assert not bad, f"Issues missing the 'regression' label: {bad}"

    def test_failed_cases_exist_in_csv(self, csv_rows: list[dict], issues: list[dict]) -> None:
        csv_keys = {_case_key(row) for row in csv_rows}
        orphans: list[tuple[str, dict]] = []
        for issue in issues:
            issue_id = _normalize_issue_id(issue.get("issue_id"))
            for case in issue.get("failed_cases") or []:
                if _case_key(case) not in csv_keys:
                    orphans.append((issue_id, case))
        assert not orphans, "failed_cases in issues.yaml that do not exist in regressions.csv:\n" + "\n".join(
            f"  issue {iid}: {case}" for iid, case in orphans
        )
