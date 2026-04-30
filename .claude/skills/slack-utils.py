#!/usr/bin/env python3
"""Shared Slack helpers for Claude skills."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

SLACK_API = "https://slack.com/api"
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
EMAIL_MENTION_RE = re.compile(r"@([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![A-Za-z0-9._%+-])")
GITHUB_ISSUE_RE = re.compile(r"/issues/(\d+)(?:$|[?#])")
GITHUB_PR_RE = re.compile(r"/pull/(\d+)(?:$|[?#])")
GITHUB_RUN_ID_RE = re.compile(r"\[(\d+)\]")
GITHUB_REPO_URL_RE = re.compile(r"^(https://github\.com/[^/]+/[^/]+)/(?:issues|pull)/\d+(?:$|[?#])")


@dataclass(frozen=True)
class SlackConfig:
    token: str
    channel_id: str


class SlackApiError(Exception):
    """Raised when Slack returns an unsuccessful API response."""


def slack_request(
    method: str,
    token: str,
    *,
    query: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{SLACK_API}/{method}"
    if query:
        url = f"{url}?{query}"

    data = None
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"

    request = Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")

    try:
        with urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise SlackApiError(f"Slack HTTP error {e.code}: {error_body}") from e
    except URLError as e:
        raise SlackApiError(f"Slack request failed: {e.reason}") from e

    try:
        result = json.loads(body)
    except json.JSONDecodeError as e:
        raise SlackApiError(f"Slack returned non-JSON response: {body}") from e

    if not result.get("ok"):
        raise SlackApiError(f"Slack API method {method} failed: {result.get('error', result)}")

    return result


def lookup_slack_mention(email: str, token: str) -> str:
    result = slack_request("users.lookupByEmail", token, query=f"email={quote(email)}")
    user_id = result.get("user", {}).get("id")
    if not user_id:
        raise SlackApiError(f"Slack user lookup for {email} did not return a user id")
    return f"<@{user_id}>"


def replace_email_mentions(message: str, token: str) -> str:
    replacements: dict[str, str] = {}

    for email in dict.fromkeys(EMAIL_MENTION_RE.findall(message)):
        try:
            replacements[email] = lookup_slack_mention(email, token)
        except SlackApiError as e:
            print(f"warning: could not resolve {email}: {e}", file=sys.stderr)
            replacements[email] = f"@{email}"

    def replace(match: re.Match[str]) -> str:
        return replacements[match.group(1)]

    return EMAIL_MENTION_RE.sub(replace, message)


def normalize_pic_mentions(pic: str | list[str]) -> str:
    if isinstance(pic, list):
        raw_values = pic
    else:
        raw_values = pic.replace(",", " ").split()

    mentions: list[str] = []
    for raw_value in raw_values:
        value = str(raw_value).strip()
        if not value:
            continue
        if EMAIL_RE.match(value):
            mentions.append(f"@{value}")
        else:
            mentions.append(value)

    return " ".join(mentions)


def slack_link(url: str, label: str) -> str:
    if not url:
        return "not provided"
    return f"<{url}|{label}>"


def issue_link(url: str) -> str:
    match = GITHUB_ISSUE_RE.search(url)
    label = f"#{match.group(1)}" if match else "Issue"
    return slack_link(url, label)


def pr_link(url: str) -> str:
    match = GITHUB_PR_RE.search(url)
    label = f"#{match.group(1)}" if match else "PR"
    return slack_link(url, label)


def infer_github_repo_url(notification: dict[str, Any]) -> str | None:
    for issue in notification.get("issues", []):
        for key in ("issue", "pr"):
            match = GITHUB_REPO_URL_RE.search(str(issue.get(key, "")))
            if match:
                return match.group(1)
    return None


def workflow_run_url(run_id: str, notification: dict[str, Any]) -> str | None:
    explicit_url = os.environ.get("GITHUB_RUN_URL")
    if explicit_url:
        return explicit_url

    repository = os.environ.get("GITHUB_REPOSITORY")
    if repository:
        server_url = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        return f"{server_url}/{repository}/actions/runs/{run_id}"

    repo_url = infer_github_repo_url(notification)
    if repo_url:
        return f"{repo_url}/actions/runs/{run_id}"

    return None


def expand_github_run_id_placeholders(title: str) -> str:
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not run_id:
        return title
    return title.replace("${GITHUB_RUN_ID}", run_id).replace("$GITHUB_RUN_ID", run_id)


def link_workflow_run_in_title(title: str, notification: dict[str, Any]) -> str:
    title = expand_github_run_id_placeholders(title)

    def replace(match: re.Match[str]) -> str:
        run_id = match.group(1)
        run_url = workflow_run_url(run_id, notification)
        if not run_url:
            return match.group(0)
        return slack_link(run_url, f"[{run_id}]")

    return GITHUB_RUN_ID_RE.sub(replace, title)


def format_issue_detail(issue: dict[str, Any], index: int) -> str:
    title = str(issue["title"]).strip()
    description = str(issue["description"]).strip()
    issue_url = str(issue["issue"]).strip()
    pr_url = str(issue["pr"]).strip()
    pic = normalize_pic_mentions(issue["pic"])

    lines = [
        f"{index}. *{title}*",
        f"_{description}_",
        f"Issue: {issue_link(issue_url)} | PR: {pr_link(pr_url)}",
    ]
    if pic:
        lines.append(f"cc {pic}")

    return "\n".join(lines)


def format_issue_details(issues: list[dict[str, Any]]) -> list[str]:
    return [format_issue_detail(issue, index) for index, issue in enumerate(issues, start=1)]


def build_summary_payload(
    channel_id: str,
    title: str,
    description: str,
    notification: dict[str, Any],
) -> dict[str, Any]:
    title = expand_github_run_id_placeholders(title)
    linked_title = link_workflow_run_in_title(title, notification)
    return {
        "channel": channel_id,
        "text": f"{title}: {description}",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{linked_title}*\n{description}",
                },
            },
        ],
    }


def build_details_payload(channel_id: str, details: str, thread_ts: str) -> dict[str, Any]:
    return {
        "channel": channel_id,
        "thread_ts": thread_ts,
        "text": details,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": details,
                },
            }
        ],
    }


def build_notification_payloads(
    channel_id: str,
    notification: dict[str, Any],
    *,
    token: str | None = None,
    thread_ts: str = "<summary message ts>",
    ending_message: str | None = None,
) -> dict[str, Any]:
    title = str(notification["title"]).strip()
    description = str(notification["description"]).strip()
    details = format_issue_details(notification["issues"])

    if token:
        description = replace_email_mentions(description, token)
        details = [replace_email_mentions(detail, token) for detail in details]
        if ending_message:
            ending_message = replace_email_mentions(ending_message, token)

    payloads = {
        "summary": build_summary_payload(channel_id, title, description, notification),
        "details": [build_details_payload(channel_id, detail, thread_ts) for detail in details],
    }
    if ending_message:
        payloads["ending"] = build_details_payload(channel_id, ending_message, thread_ts)

    return payloads


def post_message(config: SlackConfig, payload: dict[str, Any]) -> dict[str, Any]:
    return slack_request("chat.postMessage", config.token, payload=payload)


def post_notification(
    config: SlackConfig,
    notification: dict[str, Any],
    *,
    ending_message: str | None = None,
) -> dict[str, Any]:
    payloads = build_notification_payloads(
        config.channel_id,
        notification,
        token=config.token,
        ending_message=ending_message,
    )
    summary_response = post_message(config, payloads["summary"])
    thread_ts = summary_response.get("ts")
    if not thread_ts:
        raise SlackApiError("Slack summary post did not return a thread timestamp")

    detail_responses: list[dict[str, Any]] = []
    for payload in payloads["details"]:
        details_payload = dict(payload)
        details_payload["thread_ts"] = thread_ts
        detail_responses.append(post_message(config, details_payload))

    ending_response = None
    if "ending" in payloads:
        ending_payload = dict(payloads["ending"])
        ending_payload["thread_ts"] = thread_ts
        ending_response = post_message(config, ending_payload)

    return {
        "ok": True,
        "channel": summary_response.get("channel"),
        "summary_ts": thread_ts,
        "details_ts": [response.get("ts") for response in detail_responses],
        "ending_ts": ending_response.get("ts") if ending_response else None,
    }
