#!/usr/bin/env python3
"""Observe mapped GitHub source files; persist observations in a single Issue.

No upstream code is downloaded or executed. Default mode only reads GitHub.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import time
from urllib import error, parse, request

STATE_BEGIN = "<!-- x-mansion-skill-update-state:begin -->"
STATE_END = "<!-- x-mansion-skill-update-state:end -->"
STATUS_BEGIN = "<!-- x-mansion-skill-update-status:begin -->"
STATUS_END = "<!-- x-mansion-skill-update-status:end -->"
EVENT_PREFIX = "<!-- x-mansion-skill-update-event:"
TITLE = "外部 Skill 更新汇总（只通知，不自动升级）"
REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
SHA_RE = re.compile(r"[0-9a-f]{40,64}\Z")
LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\Z")


class ApiError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubAPI:
    def __init__(self, token=None):
        if token and (not token.isascii() or any(ord(char) < 33 or ord(char) > 126 for char in token)):
            raise ValueError("Invalid GitHub token format")
        self.token = token
        self.opener = request.build_opener(NoRedirect())

    def _request(self, method, path, data=None):
        if not path.startswith("/") or path.startswith("//") or "\n" in path:
            raise ValueError("GitHub API path must be relative")
        url = "https://api.github.com" + path
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "x-mansion-skill-monitor", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        payload = None if data is None else json.dumps(data).encode("utf-8")
        if payload is not None:
            headers["Content-Type"] = "application/json"
        attempts = 3 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                req = request.Request(url, data=payload, headers=headers, method=method)
                with self.opener.open(req, timeout=30) as response:
                    return json.load(response)
            except error.HTTPError as exc:
                retry = exc.code in (429, 500, 502, 503, 504)
                if retry and attempt + 1 < attempts:
                    time.sleep(2 ** attempt)
                    continue
                # Do not echo server text, request headers, or credentials.
                raise ApiError(exc.code, "GitHub HTTP %s for %s" % (exc.code, path)) from None
            except (error.URLError, TimeoutError, OSError):
                if attempt + 1 < attempts:
                    time.sleep(2 ** attempt)
                    continue
                raise ApiError(0, "GitHub network request failed for " + path) from None

    def get(self, path):
        return self._request("GET", path)

    def post(self, path, data):
        return self._request("POST", path, data)

    def patch(self, path, data):
        return self._request("PATCH", path, data)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _relative(value):
    if not isinstance(value, str) or not value or value.startswith("/") or ".." in PurePosixPath(value).parts or "\\" in value or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid mapping path")
    return value.rstrip("/")


def load_sources(root):
    root = Path(root)
    grouped = {}
    with (root / "governance/skills-registry.csv").open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("type") == "skill" and row.get("source_type") == "external" and row.get("status") != "deprecated":
                key = row.get("source_key", "")
                if not re.fullmatch(r"[A-Za-z0-9_.-]+", key) or key in (".", ".."):
                    raise ValueError("Invalid external source_key")
                grouped.setdefault(key, []).append(row["skill"])
    sources = []
    for key, skills in sorted(grouped.items()):
        manifest = json.loads((root / "governance/sources" / (key + ".json")).read_text(encoding="utf-8"))
        match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?", manifest.get("repo", ""))
        if manifest.get("kind") != "git" or not match:
            raise ValueError("Unsupported GitHub source: " + key)
        mappings = manifest.get("mappings", [])
        if not mappings:
            raise ValueError("Missing mappings for " + key)
        for mapping in mappings:
            _relative(mapping["from"])
            _relative(mapping["to"])
            if mapping.get("type") not in ("file", "dir") or not isinstance(mapping.get("exclude", []), list):
                raise ValueError("Invalid mapping for " + key)
        ref = manifest.get("ref", "")
        if not isinstance(ref, str) or not ref or any(ord(c) < 32 for c in ref):
            raise ValueError("Invalid ref for " + key)
        source = {"key": key, "skills": sorted(skills), "repo": match.group(1), "ref": ref, "mappings": mappings}
        source["config_hash"] = digest(source)
        sources.append(source)
    return sources


def _pages(get, path):
    result = []
    for page in range(1, 101):
        batch = get(path + ("&" if "?" in path else "?") + "per_page=100&page=" + str(page))
        if not isinstance(batch, list):
            raise ValueError("Expected GitHub list response")
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise ValueError("GitHub pagination limit exceeded")


def _excluded(path, patterns):
    # Same Path.match + directory-prefix rules as source-manager.should_exclude.
    return any(Path(path).match(pattern) or path == pattern or path.startswith(pattern.rstrip("/") + "/") for pattern in patterns)


def _mapped_files(source, tree, required=True):
    if tree.get("truncated") is not False:
        raise ValueError("Git tree is truncated or incomplete")
    blobs = {item["path"]: item["sha"] for item in tree["tree"] if item.get("type") == "blob"}
    selected = {}
    for mapping in source["mappings"]:
        origin = mapping["from"].rstrip("/")
        matches = {}
        for path, sha in blobs.items():
            if mapping["type"] == "file" and path == origin:
                matches[path] = sha
            elif mapping["type"] == "dir" and path.startswith(origin + "/"):
                rel = path[len(origin) + 1:]
                if not _excluded(rel, mapping.get("exclude", [])):
                    matches[path] = sha
        exists = bool(matches)
        if mapping["type"] == "dir":
            exists = any(path.startswith(origin + "/") for path in blobs) or any(
                item.get("path") == origin and item.get("type") == "tree" for item in tree["tree"]
            )
        if required and not mapping.get("optional", False) and not exists:
            raise ValueError("Required upstream mapping missing: " + origin)
        selected.update(matches)
    return selected


def _event(source, kind, before, after, paths, cycle=None):
    event = {"kind": kind, "source": source["key"], "skills": source["skills"], "repo": source["repo"], "before": before, "after": after, "paths": sorted(paths)}
    event["url"] = "https://github.com/" + source["repo"]
    if kind in ("branch", "release"):
        event["url"] += "/compare/" + parse.quote(before, safe="") + "..." + parse.quote(after, safe="")
    event["id"] = digest([source["key"], source["config_hash"], kind, before, after, sorted(paths), cycle])
    return event


def scan_sources(sources, previous_state, api):
    previous_state = previous_state or {"version": 1, "sources": {}}
    _validate_state(previous_state)
    state = copy.deepcopy(previous_state)
    active_keys = {source["key"] for source in sources}
    state["sources"] = {key: value for key, value in state["sources"].items() if key in active_keys}
    report = {"state": state, "events": [], "errors": [], "baselined": []}
    cache = {}

    def get(path):
        if path not in cache:
            try:
                cache[path] = (True, api.get(path))
            except (ApiError, ValueError) as exc:
                cache[path] = (False, exc)
        okay, value = cache[path]
        if not okay:
            raise value
        return value

    for source in sources:
        key = source["key"]
        old = previous_state["sources"].get(key, {})
        try:
            base = "/repos/" + source["repo"]

            def commit(ref):
                sha = get(base + "/commits/" + parse.quote(ref, safe=""))["sha"]
                if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
                    raise ValueError("Invalid Git commit SHA")
                return sha

            def files(sha, required=True):
                return _mapped_files(source, get(base + "/git/trees/" + sha + "?recursive=1"), required)

            current_commit = commit(source["ref"])
            current_files = files(current_commit)
            current = {"config_hash": source["config_hash"], "ref": source["ref"], "commit": current_commit, "branch_digest": digest(current_files), "release": None, "failure_cycle": old.get("failure_cycle", 0)}
            releases = [item for item in _pages(get, base + "/releases") if not item.get("draft") and not item.get("prerelease")]
            release_files = None
            if releases:
                latest = max(releases, key=lambda item: (item.get("published_at") or "", item.get("id", 0)))
                tag = latest["tag_name"]
                release_commit = commit(tag)
                release_files = files(release_commit, required=False)
                current["release"] = {"tag": tag, "commit": release_commit, "digest": digest(release_files)}

            def changed_paths(prior_commit, new_files):
                try:
                    before_files = files(prior_commit, required=False)
                except ApiError:
                    # Old commits can be removed upstream; keep the observed change.
                    return [mapping["from"] for mapping in source["mappings"]]
                return [path for path in set(before_files) | set(new_files) if before_files.get(path) != new_files.get(path)]

            events = []
            if old.get("config_hash") != source["config_hash"] or "branch_digest" not in old:
                report["baselined"].append(key)
            else:
                if old["branch_digest"] != current["branch_digest"]:
                    events.append(_event(source, "branch", old["commit"], current_commit, changed_paths(old["commit"], current_files)))
                prior_release = old.get("release")
                new_release = current["release"]
                if new_release:
                    prior_digest = prior_release["digest"] if prior_release else old["branch_digest"]
                    prior_commit = prior_release["commit"] if prior_release else old["commit"]
                    if prior_digest != new_release["digest"]:
                        event = _event(source, "release", prior_commit, new_release["commit"], changed_paths(prior_commit, release_files))
                        event["before_version"] = prior_release["tag"] if prior_release else old["ref"]
                        event["after_version"] = new_release["tag"]
                        events.append(event)
            if old.get("failure", {}).get("count", 0) >= 3:
                events.append(_event(source, "recovery", "检查失败", "检查恢复", [], old["failure"]["cycle"]))
            state["sources"][key] = current
            report["events"].extend(events)
        except (ApiError, ValueError, KeyError, TypeError) as exc:
            message = str(exc)[:500]
            signature = digest([source["config_hash"], type(exc).__name__, getattr(exc, "status", None), message])
            failed = copy.deepcopy(old)
            prior_failure = old.get("failure", {})
            same = prior_failure.get("signature") == signature
            cycle = prior_failure.get("cycle", 1) if same else old.get("failure_cycle", 0) + 1
            count = prior_failure.get("count", 0) + 1 if same else 1
            failed["failure_cycle"] = cycle
            failed["failure"] = {"signature": signature, "count": count, "message": message, "cycle": cycle, "ref": source["ref"]}
            state["sources"][key] = failed
            report["errors"].append({"source": key, "message": message, "count": count})
            if count == 3:
                event = _event(source, "error", "连续检查失败", message, [], cycle)
                report["events"].append(event)
    return report


def _validate_state(state):
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("sources"), dict):
        raise ValueError("Invalid monitor state; refusing to reset baseline")
    for key, value in state["sources"].items():
        if not isinstance(value, dict) or not ("branch_digest" in value or "failure" in value):
            raise ValueError("Invalid source observation: " + str(key))
        if "branch_digest" in value and not all(isinstance(value.get(field), str) for field in ("config_hash", "ref", "commit", "branch_digest")):
            raise ValueError("Invalid source observation: " + str(key))
        if "branch_digest" in value and (not SHA_RE.fullmatch(value["commit"]) or not re.fullmatch(r"[0-9a-f]{64}", value["branch_digest"])):
            raise ValueError("Invalid source digest or commit: " + str(key))
        release = value.get("release")
        if release is not None and (not isinstance(release, dict) or not all(isinstance(release.get(field), str) for field in ("tag", "commit", "digest"))):
            raise ValueError("Invalid release observation: " + str(key))
        if release is not None and (not SHA_RE.fullmatch(release["commit"]) or not re.fullmatch(r"[0-9a-f]{64}", release["digest"])):
            raise ValueError("Invalid release digest or commit: " + str(key))
        if not isinstance(value.get("failure_cycle", 0), int) or value.get("failure_cycle", 0) < 0:
            raise ValueError("Invalid failure cycle: " + str(key))
        failure = value.get("failure")
        if failure is not None and (not isinstance(failure, dict) or not isinstance(failure.get("count"), int) or failure["count"] < 1 or not isinstance(failure.get("cycle"), int) or failure["cycle"] < 1 or not isinstance(failure.get("signature"), str) or not isinstance(failure.get("message"), str)):
            raise ValueError("Invalid failure observation: " + str(key))


def parse_state(body):
    if body.count(STATE_BEGIN) != 1 or body.count(STATE_END) != 1 or body.index(STATE_BEGIN) >= body.index(STATE_END):
        raise ValueError("Missing or duplicate monitor state markers; refusing to reset baseline")
    raw = body.split(STATE_BEGIN, 1)[1].split(STATE_END, 1)[0].strip()
    if not raw.startswith("<!--\n") or not raw.endswith("\n-->"):
        raise ValueError("Invalid hidden monitor state")
    state = json.loads(raw[5:-4])
    _validate_state(state)
    return state


def _status_block(state):
    lines = [STATUS_BEGIN, "当前覆盖 **%s** 个外部来源。观察版本仅用于通知，不表示已升级。" % len(state["sources"]), "", "| 来源 | 已采用 ref | 已观察 commit | 最新正式 Release | 检查状态 |", "| --- | --- | --- | --- | --- |"]
    for key, source in sorted(state["sources"].items()):
        failure = source.get("failure")
        status = "正常" if not failure else "连续失败 %s 次：%s" % (failure["count"], failure["message"])
        ref = failure.get("ref", source.get("ref", "—")) if failure else source.get("ref", "—")
        release = source.get("release")
        cells = [key, ref, source.get("commit", "—")[:12], release["tag"] if release else "暂无", status]
        lines.append("| " + " | ".join(_safe_text(cell) for cell in cells) + " |")
    return "\n".join(lines + [STATUS_END])


def render_body(body, state):
    _validate_state(state)
    raw = json.dumps(state, ensure_ascii=True, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("@", "\\u0040")
    block = STATE_BEGIN + "\n<!--\n" + raw + "\n-->\n" + STATE_END
    status = _status_block(state)
    if body:
        parse_state(body)
        result = body.split(STATE_BEGIN, 1)[0] + block + body.split(STATE_END, 1)[1]
        if STATUS_BEGIN in body or STATUS_END in body:
            if body.count(STATUS_BEGIN) != 1 or body.count(STATUS_END) != 1 or body.index(STATUS_BEGIN) >= body.index(STATUS_END):
                raise ValueError("Invalid managed status markers")
            # The status must remain outside the hidden JSON state block.
            if not (body.index(STATUS_END) < body.index(STATE_BEGIN) or body.index(STATUS_BEGIN) > body.index(STATE_END)):
                raise ValueError("Overlapping managed Issue regions")
            result = result.split(STATUS_BEGIN, 1)[0] + status + result.split(STATUS_END, 1)[1]
        else:
            result = result.replace(STATE_BEGIN, status + "\n\n" + STATE_BEGIN, 1)
    else:
        result = "每日只读检查已登记的外部 Skill。首次建立观察基线，此后仅通知相关映射文件变化。不会自动升级或覆盖本地适配。\n\n" + status + "\n\n" + block
    if len(result) > 65000:
        raise ValueError("Monitor Issue body exceeds safe GitHub size limit")
    return result


def find_issue(api, repo):
    matches = []
    for issue in _pages(api.get, "/repos/" + repo + "/issues?state=all"):
        user = issue.get("user", {})
        if issue.get("pull_request") or user.get("login") != "github-actions[bot]" or user.get("type") != "Bot":
            continue
        body = issue.get("body") or ""
        if STATE_BEGIN in body or STATE_END in body or issue.get("title") == TITLE:
            parse_state(body)
            matches.append(issue)
    if len(matches) > 1:
        raise ValueError("Multiple monitor Issues found; refusing ambiguous state")
    return matches[0] if matches else None


def _safe_text(value):
    # Upstream names/paths must never generate mentions, HTML or Markdown links.
    value = str(value).replace("@", "＠").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_[\]()!|])", r"\\\1", value).replace("\n", " ").replace("\r", " ")


def _comment(events, notify_users):
    lines = ["外部 Skill 巡检发现以下变化；请人工评估是否升级。"]
    if notify_users:
        lines.append(" ".join("@" + user for user in notify_users))
    for event in events:
        label = {"branch": "上游文件更新", "release": "正式 Release 相关更新", "error": "连续检查失败", "recovery": "检查恢复"}[event["kind"]]
        lines.extend(["", "- **" + label + "** · " + _safe_text(event["source"]) + " · Skill：" + ", ".join(_safe_text(skill) for skill in event["skills"]), "  - " + _safe_text(event.get("before_version", event["before"])) + " → " + _safe_text(event.get("after_version", event["after"]))])
        if event["kind"] in ("branch", "release"):
            # Reconstruct links rather than trusting caller/upstream metadata.
            if not REPO_RE.fullmatch(event["repo"]) or not all(SHA_RE.fullmatch(event[field]) for field in ("before", "after")):
                raise ValueError("Invalid event repository or commit")
            url = "https://github.com/" + event["repo"] + "/compare/" + event["before"] + "..." + event["after"]
            lines.append("  - [查看上游差异](" + url + ")")
        paths = event.get("paths", [])
        if paths:
            lines.append("  - 相关路径：" + ", ".join(_safe_text(path) for path in paths[:30]) + (" 等 %s 项" % len(paths) if len(paths) > 30 else ""))
        lines.append(EVENT_PREFIX + event["id"] + " -->")
    return "\n".join(lines)


def publish_report(api, repo, issue, report, notify_users=None):
    notify_users = sorted(set(notify_users or []))
    if any(not LOGIN_RE.fullmatch(user) for user in notify_users):
        raise ValueError("Invalid GitHub notification username")
    body = render_body(issue.get("body") or "" if issue else "", report["state"])
    base = "/repos/" + repo + "/issues"
    if issue is None:
        # First run only creates a baseline, with no historical update comment.
        payload = {"title": TITLE, "body": body}
        if notify_users:
            payload["assignees"] = notify_users
        return api.post(base, payload)
    endpoint = base + "/" + str(issue["number"])
    events = report["events"]
    pending = events
    if events:
        comments = _pages(api.get, endpoint + "/comments")
        seen = set()
        for comment in comments:
            if comment.get("user", {}).get("login") == "github-actions[bot]":
                seen.update(re.findall(re.escape(EVENT_PREFIX) + r"([0-9a-f]{64}) -->", comment.get("body") or ""))
        pending = [event for event in events if event["id"] not in seen]
        if pending:
            comment_body = _comment(pending, notify_users)
            if len(comment_body) > 65000:
                raise ValueError("Summary comment exceeds safe GitHub size limit")
            api.post(endpoint + "/comments", {"body": comment_body})
    update = {}
    if body != (issue.get("body") or ""):
        update["body"] = body
    if pending and issue.get("state") == "closed":
        update["state"] = "open"
    assigned = {item["login"] for item in issue.get("assignees", [])}
    if set(notify_users) - assigned:
        update["assignees"] = sorted(assigned | set(notify_users))
    return api.patch(endpoint, update) if update else issue


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--repo", required=True, help="GitHub repository containing the summary Issue (owner/repo)")
    parser.add_argument("--publish", action="store_true", help="Actions only: publish state and notifications with its native GITHUB_TOKEN")
    parser.add_argument("--json", action="store_true", help="Print the machine-readable report")
    parser.add_argument("--output", type=Path, help="Also write a JSON report to this file")
    parser.add_argument("--notify-user", action="append", default=[])
    args = parser.parse_args(argv)
    report = {}
    try:
        if not REPO_RE.fullmatch(args.repo):
            raise ValueError("Invalid target owner/repo")
        users = args.notify_user + [value.strip() for value in os.environ.get("SKILL_UPDATE_NOTIFY", "").split(",") if value.strip()]
        if any(not LOGIN_RE.fullmatch(user) for user in users):
            raise ValueError("Invalid GitHub notification username")
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if args.publish and os.environ.get("GITHUB_ACTIONS") != "true":
            raise ValueError("Publishing is supported only in GitHub Actions with its native GITHUB_TOKEN; use local dry-run")
        if args.publish and not os.environ.get("GITHUB_TOKEN"):
            raise ValueError("Publishing requires the native Actions GITHUB_TOKEN")
        api = GitHubAPI(token)
        sources = load_sources(args.root)
        issue = find_issue(api, args.repo)
        state = parse_state(issue["body"]) if issue else None
        report = scan_sources(sources, state, api)
        report["mode"] = "publish" if args.publish else "dry-run"
        report["source_count"] = len(sources)
        if args.publish:
            result = publish_report(api, args.repo, issue, report, users)
            report["issue_number"] = result["number"]
        elif issue:
            report["issue_number"] = issue["number"]
        code = 1 if report["errors"] else 0
    except (ApiError, ValueError, OSError, KeyError, TypeError) as exc:
        report["fatal_error"] = str(exc)
        code = 1
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    if args.json:
        print(output)
    else:
        print("Sources: %s; events: %s; errors: %s; mode: %s" % (report.get("source_count", 0), len(report.get("events", [])), len(report.get("errors", [])), "publish" if args.publish else "dry-run"))
        if "fatal_error" in report:
            print(report["fatal_error"], file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
