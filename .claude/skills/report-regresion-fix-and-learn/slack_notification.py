#!/usr/bin/env python3
"""Validate and send support-matrix Slack notifications from JSON."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

REQUIRED_TOP_LEVEL_KEYS = ("title", "description", "issues")
REQUIRED_ISSUE_KEYS = ("title", "description", "issue", "pr", "pic")
ENDING_MESSAGE = "Comment in the PR/issue for the agent to follow up."


def load_slack_utils():
    utils_path = Path(__file__).resolve().parents[1] / "slack-utils.py"
    spec = importlib.util.spec_from_file_location("slack_utils", utils_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Slack utilities from {utils_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["slack_utils"] = module
    spec.loader.exec_module(module)
    return module


slack_utils = load_slack_utils()


class NotificationValidationError(Exception):
    """Raised when notification JSON does not match the expected schema."""


def _require_string(payload: dict[str, Any], key: str, path: str, *, allow_empty: bool = False) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise NotificationValidationError(f"{path}.{key} must be a string")
    if not allow_empty and not value.strip():
        raise NotificationValidationError(f"{path}.{key} must not be empty")
    return value


def _validate_pic(value: Any, path: str) -> None:
    if isinstance(value, str):
        if not value.strip():
            raise NotificationValidationError(f"{path}.pic must not be empty")
        return

    if isinstance(value, list):
        if not value:
            raise NotificationValidationError(f"{path}.pic must not be empty")
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                raise NotificationValidationError(f"{path}.pic[{index}] must be a non-empty string")
        return

    raise NotificationValidationError(f"{path}.pic must be a string or list of strings")


def validate_notification(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise NotificationValidationError("notification payload must be a JSON object")

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in payload:
            raise NotificationValidationError(f"notification payload is missing required key: {key}")

    _require_string(payload, "title", "payload")
    _require_string(payload, "description", "payload")

    issues = payload["issues"]
    if not isinstance(issues, list):
        raise NotificationValidationError("payload.issues must be a list")
    if not issues:
        raise NotificationValidationError("payload.issues must contain at least one issue")

    for index, issue in enumerate(issues):
        issue_path = f"payload.issues[{index}]"
        if not isinstance(issue, dict):
            raise NotificationValidationError(f"{issue_path} must be an object")

        for key in REQUIRED_ISSUE_KEYS:
            if key not in issue:
                raise NotificationValidationError(f"{issue_path} is missing required key: {key}")

        _require_string(issue, "title", issue_path)
        _require_string(issue, "description", issue_path)
        _require_string(issue, "issue", issue_path, allow_empty=True)
        _require_string(issue, "pr", issue_path, allow_empty=True)
        _validate_pic(issue["pic"], issue_path)

    return payload


def read_notification(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError as e:
        raise NotificationValidationError(f"notification JSON file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise NotificationValidationError(f"notification JSON is invalid: {e}") from e

    return validate_notification(payload)


def write_payloads(path: str, payloads: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payloads, f, indent=2, sort_keys=True)
        f.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a support-matrix notification JSON file and optionally post it to Slack.",
    )
    parser.add_argument(
        "json_file",
        nargs="?",
        default="notification.json",
        help="Notification JSON file to validate/send. Defaults to notification.json.",
    )
    parser.add_argument(
        "--channel-id",
        default=os.environ.get("SLACK_CHANNEL_ID"),
        help="Slack channel ID. Defaults to SLACK_CHANNEL_ID.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("SLACK_BOT_TOKEN"),
        help="Slack bot token. Defaults to SLACK_BOT_TOKEN.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write generated chat.postMessage payloads.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the JSON and print generated Slack payloads without posting.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        notification = read_notification(args.json_file)
    except NotificationValidationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.dry_run:
        channel_id = args.channel_id or "DRY_RUN_CHANNEL"
        payloads = slack_utils.build_notification_payloads(
            channel_id,
            notification,
            ending_message=ENDING_MESSAGE,
        )
        if args.output:
            write_payloads(args.output, payloads)
        print(json.dumps(payloads, indent=2, sort_keys=True))
        return 0

    if not args.token:
        print("error: missing Slack bot token; set SLACK_BOT_TOKEN or pass --token", file=sys.stderr)
        return 2
    if not args.channel_id:
        print("error: missing Slack channel ID; set SLACK_CHANNEL_ID or pass --channel-id", file=sys.stderr)
        return 2

    try:
        result = slack_utils.post_notification(
            slack_utils.SlackConfig(token=args.token, channel_id=args.channel_id),
            notification,
            ending_message=ENDING_MESSAGE,
        )
    except slack_utils.SlackApiError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.output:
        payloads = slack_utils.build_notification_payloads(
            args.channel_id,
            notification,
            token=args.token,
            thread_ts=result["summary_ts"],
            ending_message=ENDING_MESSAGE,
        )
        write_payloads(args.output, payloads)

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
