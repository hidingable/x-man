"""Offline behavioral regression tests for the read-only upstream monitor."""
import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "skill_updates", ROOT / "scripts" / "check-skill-updates.py"
)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = monitor
SPEC.loader.exec_module(monitor)


def source(key="example", repo="owner/upstream", ref="main", mappings=None):
    return {
        "key": key,
        "skills": [key],
        "repo": repo,
        "ref": ref,
        "mappings": mappings or [
            {"type": "dir", "from": "bundle", "to": "skills/" + key,
             "exclude": ["*.html", "cache"]}
        ],
        "config_hash": "configuration-" + key,
    }


def release(tag, draft=False, prerelease=False, date="2026-10-22T00:00:00Z"):
    return {"tag_name": tag, "draft": draft, "prerelease": prerelease,
            "published_at": date, "created_at": date,
            "html_url": "https://github.com/owner/upstream/releases/tag/" + tag}


class FakeApi:
    """In-memory GitHub endpoints; unexpected routes fail instead of networking."""

    def __init__(self):
        self.calls = []
        self.refs = {}
        self.trees = {}
        self.releases = {}
        self.failures = {}
        self.issue = None
        self.comments = []
        self.counter = 0
        self.fail_issue_patch = False

    def set_head(self, repo, files, ref="main", truncated=False):
        self.counter += 1
        sha = hashlib.sha1(str(self.counter).encode()).hexdigest()
        self.refs[(repo, ref)] = sha
        self.trees[(repo, sha)] = {
            "truncated": truncated,
            "tree": [{"path": path, "type": "blob", "sha": blob}
                     for path, blob in sorted(files.items())],
        }
        return sha

    def get(self, path):
        self.calls.append(("GET", path, None))
        if path in self.failures:
            raise self.failures[path]
        parts = urlsplit(path)
        route = parts.path
        if route.endswith("/comments"):
            return copy.deepcopy(self.comments)
        if "/commits/" in route:
            prefix, ref = route.split("/commits/", 1)
            return {"sha": self.refs[(prefix.removeprefix("/repos/"), unquote(ref))]}
        if "/git/trees/" in route:
            prefix, sha = route.split("/git/trees/", 1)
            return copy.deepcopy(self.trees[(prefix.removeprefix("/repos/"), sha)])
        if route.endswith("/releases"):
            repo = route.removeprefix("/repos/").removesuffix("/releases")
            page = int(dict(x.split("=") for x in parts.query.split("&"))["page"])
            return copy.deepcopy(self.releases.get(repo, [])[100 * (page - 1):100 * page])
        if route.endswith("/issues"):
            return [copy.deepcopy(self.issue)] if self.issue else []
        if "/issues/" in route:
            return copy.deepcopy(self.issue)
        raise AssertionError("Unexpected GET " + path)

    def post(self, path, data):
        self.calls.append(("POST", path, copy.deepcopy(data)))
        if path.endswith("/comments"):
            item = {"id": len(self.comments) + 1, "body": data["body"],
                    "user": {"login": "github-actions[bot]", "type": "Bot"}}
            self.comments.append(item)
            return copy.deepcopy(item)
        if path.endswith("/issues"):
            self.issue = {"number": 7, "state": "open", "body": data["body"],
                          "title": data.get("title", "External skill updates"),
                          "user": {"login": "github-actions[bot]", "type": "Bot"},
                          "assignees": []}
            return copy.deepcopy(self.issue)
        raise AssertionError("Unexpected POST " + path)

    def patch(self, path, data):
        self.calls.append(("PATCH", path, copy.deepcopy(data)))
        if self.fail_issue_patch and "body" in data:
            self.fail_issue_patch = False
            raise monitor.ApiError(503, "temporary issue state write failure")
        self.issue.update(data)
        if "assignees" in data:
            self.issue["assignees"] = [{"login": user} for user in data["assignees"]]
        return copy.deepcopy(self.issue)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        self.src = source()
        self.files = {"bundle/SKILL.md": "old", "bundle/guide.md": "guide",
                      "bundle/demo.html": "html", "bundle/cache/blob": "cache",
                      "unrelated/README.md": "unrelated"}
        self.api.set_head(self.src["repo"], self.files)

    def scan(self, previous=None, sources=None):
        return monitor.scan_sources(sources or [self.src], previous, self.api)

    def baseline(self):
        result = self.scan()
        self.assertFalse(result["errors"], result)
        self.assertFalse(result["events"], result)
        return result["state"]

    def update(self, **files):
        self.files.update(files)
        self.api.set_head(self.src["repo"], self.files)

    def test_first_observation_silently_builds_baseline(self):
        report = self.scan()
        self.assertFalse(report["events"])
        self.assertFalse(report["errors"])
        self.assertIn(self.src["key"], report["state"]["sources"])
        self.assertTrue(report["baselined"])
        self.assertFalse(any(method != "GET" for method, _, _ in self.api.calls))

    def test_all_sources_share_repository_ref_requests(self):
        sources = monitor.load_sources(ROOT)
        self.assertEqual(len(list((ROOT / "governance" / "sources").glob("*.json"))), len(sources))
        grouped = {}
        for item in sources:
            files = grouped.setdefault((item["repo"], item["ref"]), {})
            for mapping in item["mappings"]:
                path = mapping["from"]
                if mapping["type"] == "dir":
                    path = path.rstrip("/") + "/fixture.txt"
                files[path] = "upstream-blob"
        for (repo, ref), files in grouped.items():
            self.api.set_head(repo, files, ref)
        report = self.scan(sources=sources)
        self.assertFalse(report["errors"], report)
        counts = Counter(path for method, path, _ in self.api.calls if method == "GET")
        self.assertTrue(counts)
        self.assertTrue(all(count == 1 for count in counts.values()), counts)
        self.assertLess(len(grouped), len(sources))

    def test_changed_imported_blob_emits_branch_event(self):
        state = self.baseline()
        self.update(**{"bundle/SKILL.md": "new"})
        report = self.scan(state)
        self.assertEqual(["branch"], [event["kind"] for event in report["events"]])
        self.assertIn("bundle/SKILL.md", report["events"][0]["paths"])

    def test_other_directory_and_excluded_files_are_silent(self):
        state = self.baseline()
        self.update(**{"unrelated/README.md": "new", "bundle/demo.html": "new",
                       "bundle/cache/blob": "new"})
        report = self.scan(state)
        self.assertFalse(report["events"], report)
        self.assertFalse(report["errors"], report)

    def test_file_mapping_ignores_siblings_and_detects_deletion(self):
        self.src = source(mappings=[{"type": "file", "from": "bundle/SKILL.md",
                                     "to": "skills/example/UPSTREAM.md"}])
        state = self.baseline()
        self.update(**{"bundle/guide.md": "new"})
        report = self.scan(state)
        self.assertFalse(report["events"])
        del self.files["bundle/SKILL.md"]
        self.api.set_head(self.src["repo"], self.files)
        report = self.scan(report["state"])
        self.assertTrue(report["events"] or report["errors"], report)

    def test_local_skill_adaptation_does_not_determine_upstream_updates(self):
        state = self.baseline()
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("local read")), \
                mock.patch.object(Path, "read_bytes", side_effect=AssertionError("local read")):
            report = self.scan(state)
        self.assertFalse(report["events"])
        self.assertFalse(report["errors"])

    def test_pinned_tag_discovers_new_formal_release(self):
        self.src["ref"] = "v1.0.0"
        self.api.set_head(self.src["repo"], self.files, "v1.0.0")
        self.api.releases[self.src["repo"]] = [release("v1.0.0")]
        state = self.baseline()
        self.api.set_head(self.src["repo"], {**self.files, "bundle/SKILL.md": "v2"}, "v2.0.0")
        self.api.releases[self.src["repo"]].insert(0, release("v2.0.0", date="2026-10-23T00:00:00Z"))
        report = self.scan(state)
        self.assertEqual(["release"], [event["kind"] for event in report["events"]])
        self.assertIn("v2.0.0", json.dumps(report["events"]))

    def test_draft_and_prerelease_do_not_trigger_release_notice(self):
        self.src["ref"] = "v1.0.0"
        self.api.set_head(self.src["repo"], self.files, "v1.0.0")
        self.api.releases[self.src["repo"]] = [release("v1.0.0")]
        state = self.baseline()
        self.api.releases[self.src["repo"]] = [release("v3.0.0", draft=True),
            release("v2.0.0-rc.1", prerelease=True), release("v1.0.0")]
        report = self.scan(state)
        self.assertFalse(report["events"])
        self.assertFalse(report["errors"])
        self.assertFalse(any("v3.0.0" in path or "rc.1" in path
                             for method, path, _ in self.api.calls))

    def test_config_change_rebaselines_only_changed_source(self):
        other = source("other", "other/repo")
        self.api.set_head(other["repo"], {"bundle/SKILL.md": "old"})
        state = self.scan(sources=[self.src, other])["state"]
        self.src["config_hash"] = "new-configuration"
        self.update(**{"bundle/SKILL.md": "new"})
        self.api.set_head(other["repo"], {"bundle/SKILL.md": "new"})
        report = self.scan(state, [self.src, other])
        self.assertEqual(["other"], [event["source"] for event in report["events"]])
        self.assertIn("example", report["baselined"])

    def test_partial_failure_does_not_advance_failed_source(self):
        other = source("other", "other/repo")
        self.api.set_head(other["repo"], {"bundle/SKILL.md": "old"})
        sources = [self.src, other]
        state = self.scan(sources=sources)["state"]
        self.update(**{"bundle/SKILL.md": "new"})
        self.api.set_head(other["repo"], {"bundle/SKILL.md": "new"})
        self.api.failures["/repos/owner/upstream/commits/main"] = monitor.ApiError(503, "down")
        report = self.scan(state, sources)
        self.assertTrue(report["errors"])
        self.assertEqual(["other"], [event["source"] for event in report["events"]])
        del self.api.failures["/repos/owner/upstream/commits/main"]
        retry = self.scan(report["state"], sources)
        self.assertTrue(any(event["source"] == "example" and event["kind"] == "branch"
                            for event in retry["events"]), retry)
        self.assertFalse(any(event["source"] == "other" for event in retry["events"]))

    def test_truncated_tree_is_failure_and_cannot_become_baseline(self):
        state = self.baseline()
        self.api.set_head(self.src["repo"], {"bundle/SKILL.md": "new"}, truncated=True)
        report = self.scan(state)
        self.assertTrue(report["errors"])
        self.assertFalse(any(event["kind"] == "branch" for event in report["events"]))
        self.api.set_head(self.src["repo"], {"bundle/SKILL.md": "new"})
        retry = self.scan(report["state"])
        self.assertTrue(any(event["kind"] == "branch" for event in retry["events"]))

    def test_third_identical_failure_notifies_once(self):
        state = self.baseline()
        self.api.failures["/repos/owner/upstream/commits/main"] = monitor.ApiError(503, "down")
        baseline_report = {"state": state, "events": [], "errors": [], "baselined": []}
        monitor.publish_report(self.api, "local/x-mansion", None, baseline_report)
        ids = []
        for attempt in range(5):
            report = self.scan(state)
            if attempt < 2:
                self.assertFalse(report["events"])
            ids.extend(event["id"] for event in report["events"])
            monitor.publish_report(self.api, "local/x-mansion", self.api.issue, report)
            state = report["state"]
        self.assertEqual(1, len(set(ids)))
        self.assertEqual(1, len(self.api.comments))

    def test_required_directory_with_only_excluded_blobs_is_valid(self):
        self.src["mappings"][0]["exclude"] = ["*"]
        report = self.scan()
        self.assertFalse(report["errors"], report)
        self.assertFalse(report["events"], report)
        self.assertIn(self.src["key"], report["state"]["sources"])

    def test_removed_source_is_pruned_from_issue_state(self):
        other = source("removed", "other/repo")
        self.api.set_head(other["repo"], {"bundle/SKILL.md": "old"})
        state = self.scan(sources=[self.src, other])["state"]
        self.assertIn("removed", state["sources"])
        report = self.scan(state, [self.src])
        self.assertNotIn("removed", report["state"]["sources"])
        self.assertFalse(report["events"])

    def test_release_selection_uses_publish_date_not_response_order(self):
        self.api.set_head(self.src["repo"], self.files, "v1.0.0")
        self.api.releases[self.src["repo"]] = [release("v1.0.0")]
        state = self.baseline()
        self.api.set_head(self.src["repo"], {**self.files, "bundle/SKILL.md": "v2"}, "v2.0.0")
        self.api.releases[self.src["repo"]].append(release("v2.0.0", date="2026-10-23T00:00:00Z"))
        report = self.scan(state)
        updates = [event for event in report["events"] if event["kind"] == "release"]
        self.assertEqual(1, len(updates))
        self.assertEqual("v2.0.0", updates[0]["after_version"])

    def test_old_release_without_current_mapping_can_be_baselined(self):
        self.api.set_head(self.src["repo"], {"old-layout/README.md": "old"}, "v0.1.0")
        self.api.releases[self.src["repo"]] = [release("v0.1.0")]
        state = self.baseline()
        report = self.scan(state)
        self.assertFalse(report["errors"], report)
        self.assertFalse(report["events"], report)

    def test_sustained_failure_recovery_notifies_once(self):
        state = self.baseline()
        self.api.failures["/repos/owner/upstream/commits/main"] = monitor.ApiError(503, "down")
        for _ in range(3):
            state = self.scan(state)["state"]
        self.api.failures.clear()
        recovery = self.scan(state)
        self.assertEqual(["recovery"], [event["kind"] for event in recovery["events"]])
        self.assertFalse(self.scan(recovery["state"])["events"])

    def test_source_configuration_hash_tracks_manifest_not_local_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifests = root / "governance" / "sources"
            manifests.mkdir(parents=True)
            (root / "governance" / "skills-registry.csv").write_text(
                "skill,type,source_type,source_key,status\nexample,skill,external,example,experimental\n",
                encoding="utf-8")
            path = manifests / "example.json"
            manifest = {"key": "example", "kind": "git",
                        "repo": "https://github.com/owner/upstream.git", "ref": "main",
                        "mappings": self.src["mappings"]}
            path.write_text(json.dumps(manifest), encoding="utf-8")
            first = monitor.load_sources(root)
            local = root / "skills" / "example" / "SKILL.md"
            local.parent.mkdir(parents=True)
            local.write_text("local adaptation @arbitrary-user", encoding="utf-8")
            self.assertEqual(first, monitor.load_sources(root))
            manifest["mappings"][0]["exclude"].append("*.tmp")
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertNotEqual(first[0]["config_hash"], monitor.load_sources(root)[0]["config_hash"])


class PublishingTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        self.repo = "local/x-mansion"
        self.src = source()
        self.api.set_head(self.src["repo"], {"bundle/SKILL.md": "old"})
        self.baseline = monitor.scan_sources([self.src], None, self.api)

    def publish(self, report, users=None):
        return monitor.publish_report(self.api, self.repo, self.api.issue, report,
                                      notify_users=users or [])

    def create_baseline_issue(self):
        self.publish(self.baseline)
        self.assertIsNotNone(self.api.issue)
        self.assertFalse(self.api.comments)
        return self.api.issue

    def changed_report(self, previous=None):
        self.api.set_head(self.src["repo"], {"bundle/SKILL.md": "new"})
        report = monitor.scan_sources([self.src], previous or self.baseline["state"], self.api)
        self.assertTrue(report["events"])
        return report

    def test_initial_issue_persists_silent_baseline_without_comment(self):
        self.create_baseline_issue()
        self.assertEqual(self.baseline["state"], monitor.parse_state(self.api.issue["body"]))

    def test_second_identical_event_does_not_comment(self):
        self.create_baseline_issue()
        report = self.changed_report()
        self.publish(report)
        self.assertEqual(1, len(self.api.comments))
        self.publish(report)
        self.assertEqual(1, len(self.api.comments))

    def test_comment_success_state_failure_retry_does_not_duplicate(self):
        self.create_baseline_issue()
        report = self.changed_report()
        self.api.fail_issue_patch = True
        with self.assertRaises(monitor.ApiError):
            self.publish(report)
        self.assertEqual(1, len(self.api.comments))
        old_state = monitor.parse_state(self.api.issue["body"])
        self.assertEqual(self.baseline["state"], old_state)
        retry = monitor.scan_sources([self.src], old_state, self.api)
        self.publish(retry)
        self.assertEqual(1, len(self.api.comments))
        self.assertEqual(retry["state"], monitor.parse_state(self.api.issue["body"]))

    def test_closed_issue_stays_closed_until_new_event_then_reopens(self):
        self.create_baseline_issue()
        self.api.issue["state"] = "closed"
        self.publish(self.baseline)
        self.assertEqual("closed", self.api.issue["state"])
        self.publish(self.changed_report())
        self.assertEqual("open", self.api.issue["state"])
        self.assertEqual(1, len(self.api.comments))

    def test_duplicate_old_event_does_not_reopen_closed_issue(self):
        self.create_baseline_issue()
        report = self.changed_report()
        self.publish(report)
        self.api.issue["state"] = "closed"
        self.publish(report)
        self.assertEqual("closed", self.api.issue["state"])
        self.assertEqual(1, len(self.api.comments))

    def test_user_text_outside_managed_body_is_preserved(self):
        self.create_baseline_issue()
        prefix = "Maintainer notes: please keep this.\n\n"
        suffix = "\n\nHuman checklist: - [ ] review updates"
        self.api.issue["body"] = prefix + self.api.issue["body"] + suffix
        self.publish(self.changed_report())
        self.assertTrue(self.api.issue["body"].startswith(prefix))
        self.assertTrue(self.api.issue["body"].endswith(suffix))

    def test_corrupt_state_is_rejected_and_not_reset(self):
        for bad_json in ("{broken}", '{"version":99,"sources":{}}'):
            with self.subTest(body=bad_json):
                body = monitor.STATE_BEGIN + "\n<!--\n" + bad_json + "\n-->\n" + monitor.STATE_END
                with self.assertRaises((ValueError, RuntimeError)):
                    monitor.parse_state(body)

    def test_only_configured_users_can_be_mentioned(self):
        self.create_baseline_issue()
        report = self.changed_report()
        report["events"][0]["paths"].append("bundle/@upstream-user.md")
        report["events"][0]["before_version"] = "@stranger"
        self.publish(report, ["trusted-maintainer"])
        body = self.api.comments[0]["body"]
        self.assertIn("@trusted-maintainer", body)
        self.assertNotIn("@upstream-user", body)
        self.assertNotIn("@stranger", body)

    def test_new_notification_uses_current_configuration_only(self):
        self.create_baseline_issue()
        first = self.changed_report()
        self.publish(first, ["former-maintainer"])
        self.api.set_head(self.src["repo"], {"bundle/SKILL.md": "newer"})
        report = monitor.scan_sources([self.src], first["state"], self.api)
        self.publish(report, ["current-maintainer"])
        body = self.api.comments[-1]["body"]
        self.assertIn("@current-maintainer", body)
        self.assertNotIn("@former-maintainer", body)

    def test_cli_dry_run_never_posts_or_patches(self):
        self.create_baseline_issue()
        self.api.set_head(self.src["repo"], {"bundle/SKILL.md": "new"})
        self.api.calls.clear()
        with mock.patch.object(monitor, "GitHubAPI", return_value=self.api), \
                mock.patch.object(monitor, "load_sources", return_value=[self.src]), \
                mock.patch("builtins.print"):
            code = monitor.main(["--repo", self.repo, "--json"])
        self.assertEqual(0, code)
        self.assertTrue(self.api.calls)
        self.assertTrue(all(method == "GET" for method, _, _ in self.api.calls))

    def test_cli_publish_rejects_personal_token_outside_actions(self):
        self.api.calls.clear()
        with mock.patch.dict("os.environ", {"GITHUB_ACTIONS": "false", "GITHUB_TOKEN": "personal-token"}, clear=True), \
                mock.patch.object(monitor, "GitHubAPI", return_value=self.api), \
                mock.patch.object(monitor, "load_sources", return_value=[self.src]), \
                mock.patch("builtins.print"):
            code = monitor.main(["--repo", self.repo, "--publish", "--json"])
        self.assertEqual(1, code)
        self.assertFalse(self.api.calls)

    def test_managed_issue_title_with_missing_markers_refuses_reset(self):
        self.create_baseline_issue()
        self.api.issue["body"] = "Maintainer accidentally removed state markers"
        with self.assertRaises(ValueError):
            monitor.find_issue(self.api, self.repo)

    def test_render_same_state_preserves_all_body_bytes(self):
        body = monitor.render_body("", self.baseline["state"])
        body = "Human prefix \u2603\n" + body + "\nHuman suffix"
        self.assertEqual(body, monitor.render_body(body, self.baseline["state"]))

    def test_visible_status_lists_source_and_failures_preserving_user_text(self):
        body = monitor.render_body("", self.baseline["state"])
        status = body.split(monitor.STATUS_BEGIN, 1)[1].split(monitor.STATUS_END, 1)[0]
        self.assertIn("example", status)
        self.assertIn("main", status)
        self.assertIn("正常", status)
        self.api.failures["/repos/owner/upstream/commits/main"] = monitor.ApiError(503, "unavailable-upstream")
        failed = monitor.scan_sources([self.src], self.baseline["state"], self.api)
        prefix, suffix = "Human prefix\n", "\nHuman suffix"
        result = monitor.render_body(prefix + body + suffix, failed["state"])
        visible = result.split(monitor.STATUS_BEGIN, 1)[1].split(monitor.STATUS_END, 1)[0]
        self.assertIn("example", visible)
        self.assertIn("失败", visible)
        self.assertIn("unavailable-upstream", visible)
        self.assertTrue(result.startswith(prefix))
        self.assertTrue(result.endswith(suffix))
        self.assertEqual(failed["state"], monitor.parse_state(result))
        self.assertEqual(result, monitor.render_body(result, failed["state"]))

    def test_legacy_issue_adds_status_once_without_removing_user_text(self):
        body = monitor.render_body("", self.baseline["state"])
        before, rest = body.split(monitor.STATUS_BEGIN, 1)
        legacy = before + rest.split(monitor.STATUS_END, 1)[1]
        legacy = "Legacy user notes\n" + legacy + "\nLegacy tail"
        result = monitor.render_body(legacy, self.baseline["state"])
        self.assertEqual(1, result.count(monitor.STATUS_BEGIN))
        self.assertEqual(1, result.count(monitor.STATUS_END))
        self.assertIn("Legacy user notes", result)
        self.assertTrue(result.endswith("Legacy tail"))
        self.assertEqual(result, monitor.render_body(result, self.baseline["state"]))

    def test_broken_visible_status_markers_refuse_destructive_rewrite(self):
        body = monitor.render_body("", self.baseline["state"])
        with self.assertRaises(ValueError):
            monitor.render_body(body.replace(monitor.STATUS_END, ""), self.baseline["state"])

    def test_find_issue_ignores_human_authored_spoof(self):
        self.create_baseline_issue()
        self.api.issue["user"] = {"login": "human", "type": "User"}
        self.assertIsNone(monitor.find_issue(self.api, self.repo))

    def test_find_issue_accepts_only_managed_bot_issue(self):
        self.create_baseline_issue()
        self.assertEqual(7, monitor.find_issue(self.api, self.repo)["number"])
        self.api.issue["pull_request"] = {"url": "https://api.github.com/repos/local/x-mansion/pulls/7"}
        self.assertIsNone(monitor.find_issue(self.api, self.repo))


if __name__ == "__main__":
    unittest.main()
