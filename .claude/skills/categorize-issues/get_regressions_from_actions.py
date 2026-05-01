#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Fetch the support matrix CSV from support-matrix base and update branches
and emit a single CSV listing every regression.

Branches inspected:
    1. release/{latest_version}                   (the most recent release/* branch)
    2. automated/update-support-matrix-release/{latest_version}
    3. main                                       (baseline)
    4. automated/update-support-matrix-main       (proposed update to main)

A row is reported as a regression when the combination
    (HuggingFaceID, Architecture, System, Backend, Version, Mode)
has Status=PASS on a base branch, but Status=FAIL on its proposed update branch.

Output columns:
    HuggingFaceID, Architecture, System, Backend, Version, Mode, FailedBranch, ErrMsg
"""

import argparse
import csv
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from io import StringIO

REPO = "ai-dynamo/aiconfigurator"
CSV_PATH = "src/aiconfigurator/systems/support_matrix.csv"
RAW_URL_TMPL = f"https://raw.githubusercontent.com/{REPO}/refs/heads/{{branch}}/{CSV_PATH}"
GITHUB_API = f"https://api.github.com/repos/{REPO}/branches"
REMOTE_URL = f"https://github.com/{REPO}.git"

EXPECTED_HEADER = ["HuggingFaceID", "Architecture", "System", "Backend", "Version", "Mode", "Status", "ErrMsg"]
KEY_COLS = ("HuggingFaceID", "Architecture", "System", "Backend", "Version", "Mode")
RELEASE_RE = re.compile(r"^release/(.+)$")


def _http_get(url: str, accept: str | None = None) -> bytes:
    req = urllib.request.Request(url)
    if accept:
        req.add_header("Accept", accept)
    req.add_header("User-Agent", "aiconfigurator-get-regressions")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _version_key(text: str) -> tuple:
    """Best-effort numeric key for sorting release branch versions."""
    parts = re.split(r"[.\-_]", text)
    key = []
    for part in parts:
        m = re.match(r"^(\d+)(.*)$", part)
        if m:
            key.append((0, int(m.group(1)), m.group(2)))
        else:
            key.append((1, 0, part))
    return tuple(key)


def _release_versions_from_ls_remote() -> list[str]:
    """List release/* branches without using the GitHub REST API."""
    try:
        output = subprocess.check_output(
            ["git", "ls-remote", "--heads", "--refs", REMOTE_URL, "refs/heads/release/*"],
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as e:
        print(f"git ls-remote failed; falling back to GitHub API: {e}", file=sys.stderr)
        return []

    versions: list[str] = []
    for line in output.splitlines():
        _sha, _, ref = line.partition("\t")
        branch = ref.removeprefix("refs/heads/")
        m = RELEASE_RE.match(branch)
        if m:
            versions.append(m.group(1))
    return versions


def _release_versions_from_github_api() -> list[str]:
    """List release/* branches with the GitHub REST API."""
    versions: list[str] = []
    page = 1
    while True:
        url = f"{GITHUB_API}?per_page=100&page={page}"
        try:
            payload = _http_get(url, accept="application/vnd.github+json")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"GitHub API request failed for {url}: {e}") from e
        branches = json.loads(payload)
        if not branches:
            break
        for branch in branches:
            name = branch.get("name", "")
            m = RELEASE_RE.match(name)
            if m:
                versions.append(m.group(1))
        if len(branches) < 100:
            break
        page += 1

    return versions


def find_latest_release_branch() -> str:
    """Find the largest release/* branch version."""
    versions = _release_versions_from_ls_remote() or _release_versions_from_github_api()

    if not versions:
        raise RuntimeError(f"No release/* branches found on {REPO}")
    versions.sort(key=_version_key)
    return versions[-1]


def fetch_csv(branch: str) -> dict[tuple, dict[str, str]]:
    """Fetch and parse the support matrix CSV for a given branch.

    Returns a dict keyed by (HuggingFaceID, Architecture, System, Backend, Version, Mode)
    whose values are the row dicts.
    """
    url = RAW_URL_TMPL.format(branch=branch)
    try:
        raw = _http_get(url).decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"Skipping {branch}: {CSV_PATH} does not exist", file=sys.stderr)
            return {}
        raise RuntimeError(f"Failed to fetch {url}: {e}") from e

    reader = csv.DictReader(StringIO(raw))
    if reader.fieldnames != EXPECTED_HEADER:
        raise ValueError(f"Unexpected CSV header from {branch}: {reader.fieldnames!r} (expected {EXPECTED_HEADER!r})")

    out: dict[tuple, dict[str, str]] = {}
    for row in reader:
        key = tuple(row[c] for c in KEY_COLS)
        out[key] = row
    return out


def collect_regressions(
    base_rows: dict[tuple, dict[str, str]],
    other_rows: dict[tuple, dict[str, str]],
    failed_branch: str,
) -> list[dict[str, str]]:
    """Rows that pass on a base branch but fail on the other branch."""
    regressions: list[dict[str, str]] = []
    for key, base_row in base_rows.items():
        if base_row.get("Status") != "PASS":
            continue
        other_row = other_rows.get(key)
        if other_row is None or other_row.get("Status") != "FAIL":
            continue
        regressions.append(
            {
                "HuggingFaceID": other_row["HuggingFaceID"],
                "Architecture": other_row["Architecture"],
                "System": other_row["System"],
                "Backend": other_row["Backend"],
                "Version": other_row["Version"],
                "Mode": other_row["Mode"],
                "ErrMsg": other_row.get("ErrMsg", ""),
                "FailedBranch": failed_branch,
            }
        )
    return regressions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "-o",
        "--output",
        default="regressions.csv",
        help="Path to write the regressions CSV (default: regressions.csv).",
    )
    parser.add_argument(
        "--release-branch",
        default=None,
        help="Override release branch (e.g. 'release/0.5.0'). "
        "If omitted, the largest release/* branch is auto-detected.",
    )
    args = parser.parse_args()

    if args.release_branch:
        release_branch = args.release_branch
    else:
        latest_version = find_latest_release_branch()
        release_branch = f"release/{latest_version}"

    automated_release_branch = f"automated/update-support-matrix-{release_branch}"
    automated_main_branch = "automated/update-support-matrix-main"
    main_branch = "main"

    print("Fetching CSVs:", file=sys.stderr)
    print(f"  (1) {release_branch}", file=sys.stderr)
    print(f"  (2) {automated_release_branch}", file=sys.stderr)
    print(f"  (3) {main_branch}", file=sys.stderr)
    print(f"  (4) {automated_main_branch}", file=sys.stderr)

    release_rows = fetch_csv(release_branch)
    automated_release_rows = fetch_csv(automated_release_branch)
    main_rows = fetch_csv(main_branch)
    automated_main_rows = fetch_csv(automated_main_branch)

    regressions = []
    regressions.extend(collect_regressions(release_rows, automated_release_rows, automated_release_branch))
    regressions.extend(collect_regressions(main_rows, automated_main_rows, automated_main_branch))

    fieldnames = [
        "HuggingFaceID",
        "Architecture",
        "System",
        "Backend",
        "Version",
        "Mode",
        "FailedBranch",
        "ErrMsg",
    ]
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(regressions)

    print(
        f"Wrote {len(regressions)} regression rows to {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
