"""Forge detection from origin, and GitLab merge requests read and written through glab."""
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
spec = importlib.util.spec_from_file_location("flowctl_forge_test", SCRIPTS / "flowctl.py")
f = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = f
spec.loader.exec_module(f)

GITLAB = {"forge": "gitlab", "host": "gitlab.example.com", "project": "group/sub/proj"}


def mr(iid, state="opened", branch="fn-1-feature", **extra):
    return {"iid": iid, "web_url": f"https://gitlab.example.com/group/sub/proj/-/merge_requests/{iid}",
            "state": state, "source_branch": branch, "target_branch": "main", "sha": f"sha{iid}",
            "merged_at": None, "draft": False, "source_project_id": 7, "target_project_id": 7, **extra}


def done(stdout="", returncode=0, stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class RemoteParseTests(unittest.TestCase):
    def test_remote_urls(self):
        cases = {
            "https://user:secret@gitlab.example.com/group/sub/proj.git": ("gitlab.example.com", "group/sub/proj", False),
            "https://gitlab.example.com:8443/group/proj": ("gitlab.example.com", "group/proj", False),
            "ssh://git@GitLab.example.com:2222/group/proj.git": ("gitlab.example.com", "group/proj", True),
            "git@gitlab.com:group/proj.git": ("gitlab.com", "group/proj", True),
            "gl-work:group/proj.git": ("gl-work", "group/proj", True),
            "/srv/repos/proj.git": (None, None, False),
            "C:\\repos\\proj": (None, None, False),
            "file:///srv/repos/proj.git": (None, None, False),
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(f._remote_host_path(url), expected)


class DetectForgeTests(unittest.TestCase):
    def detect(self, origin, *, gh_ok=False, glab_ok=False, ssh_host=None):
        calls = []

        def run(argv, **_):
            calls.append(argv)
            if argv[:3] == ["git", "remote", "get-url"]:
                return done(origin + "\n") if origin else done(returncode=2)
            if argv[:2] == ["ssh", "-G"]:
                return done(f"user git\nhostname {ssh_host or argv[2]}\n")
            if argv[0] == "gh":
                return done(returncode=0 if gh_ok else 1)
            if argv[0] == "glab":
                return done(returncode=0 if glab_ok else 1)
            raise AssertionError(argv)
        with patch.object(f.subprocess, "run", side_effect=run):
            return f.detect_forge(Path(".")), calls

    def test_known_hosts_need_no_cli(self):
        for origin, forge in (("https://github.com/o/r.git", "github"), ("git@github.com:o/r.git", "github"),
                              ("https://gitlab.com/g/p.git", "gitlab"), ("git@gitlab.com:g/p.git", "gitlab")):
            with self.subTest(origin=origin):
                result, calls = self.detect(origin)
                self.assertEqual(result["forge"], forge)
                self.assertEqual(calls, [["git", "remote", "get-url", "origin"]])

    def test_self_managed_hosts_follow_the_logged_in_cli(self):
        self.assertEqual(self.detect("https://ghe.corp/o/r.git", gh_ok=True)[0]["forge"], "github")
        result, calls = self.detect("https://gitlab.example.com/group/sub/proj.git", glab_ok=True)
        self.assertEqual(result, GITLAB)
        self.assertIn(["glab", "auth", "status", "--hostname", "gitlab.example.com"], calls)
        # GitHub wins a host both CLIs claim; neither claiming it is no forge.
        self.assertEqual(self.detect("https://both.example/o/r", gh_ok=True, glab_ok=True)[0]["forge"], "github")
        self.assertIsNone(self.detect("https://git.example.com/o/r.git")[0]["forge"])
        self.assertIsNone(self.detect("")[0]["forge"])

    def test_ssh_alias_resolves_before_classifying(self):
        result, _ = self.detect("gl-work:group/proj.git", ssh_host="gitlab.com")
        self.assertEqual(result["forge"], "gitlab")
        self.assertEqual(result["host"], "gitlab.com")


class GitlabRowsTests(unittest.TestCase):
    def rows(self, *pages, returncode=0, **kwargs):
        calls = []

        def run(argv, **_):
            calls.append(argv)
            body = pages[len(calls) - 1] if len(calls) <= len(pages) else []
            # glab's config warning lands on stdout ahead of the JSON.
            return done("Multiple config files found\n" + json.dumps(body), returncode=returncode,
                        stderr="HTTP 401 Unauthorized" if returncode else "")
        with patch.object(f.subprocess, "run", side_effect=run):
            return f.gitlab_mr_rows(Path("."), GITLAB, **kwargs), calls

    def test_rows_take_gh_field_names_and_states(self):
        (rows, failure), calls = self.rows([
            mr(1), mr(2, "locked"), mr(3, "merged", merged_at="2026-11-01T00:00:00Z", merge_commit_sha="m3"),
            mr(4, "closed"), mr(5, source_project_id=99)], head="fn-1-feature")
        self.assertEqual(failure, "")
        self.assertEqual([(r["number"], r["state"]) for r in rows],
                         [(1, "OPEN"), (2, "OPEN"), (3, "MERGED"), (4, "CLOSED")])  # the fork MR is left out
        self.assertEqual(rows[2]["mergeCommit"], {"oid": "m3"})
        self.assertEqual(rows[0]["headRefName"], "fn-1-feature")
        self.assertEqual(rows[0]["headRefOid"], "sha1")
        argv = calls[0]
        self.assertEqual(argv[:4], ["glab", "api", "--hostname", "gitlab.example.com"])
        self.assertIn("projects/group%2Fsub%2Fproj/merge_requests?", argv[-1])
        self.assertIn("source_branch=fn-1-feature", argv[-1])
        self.assertIn("state=all", argv[-1])

    def test_failure_and_truncation(self):
        (rows, failure), _ = self.rows([mr(1)], returncode=1, head="x")
        self.assertIsNone(rows)
        self.assertIn("401", failure)
        (rows, _), calls = self.rows([mr(i) for i in range(100)], [mr(i) for i in range(100, 150)], limit=100)
        self.assertEqual(len(rows), 100)  # a caller requiring fewer than the limit sees truncation
        self.assertEqual(len(calls), 1)
        (rows, _), _ = self.rows([{"iid": "x"}])
        self.assertIsNone(rows)

    def test_one_mr_by_number(self):
        (rows, _), calls = self.rows(mr(7, "merged"), number=7)
        self.assertEqual(rows[0]["state"], "MERGED")
        self.assertTrue(calls[0][-1].endswith("merge_requests/7"))


class RouteProbeTests(unittest.TestCase):
    def state(self, rows, failure="down"):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            body = repo / "spec.md"
            body.write_text("Implement feature", encoding="utf-8")
            spec_data = {"title": "Feature", "status": "open", "branch_name": "fn-1-feature"}
            with patch.object(f, "get_config", return_value=True), patch.object(f, "get_repo_root", return_value=repo), \
                    patch.object(f, "get_flow_dir", return_value=repo), \
                    patch.object(f, "resolve_spec_id_arg", return_value="fn-1-feature"), \
                    patch.object(f, "load_json_or_exit", return_value=spec_data), \
                    patch.object(f, "normalize_epic", side_effect=lambda x: x), \
                    patch.object(f, "find_spec_md_path", return_value=body), \
                    patch.object(f.TaskInventory, "load", return_value=SimpleNamespace(
                        by_spec={"fn-1-feature": [{"status": "done"}]})), \
                    patch.object(f, "detect_forge", return_value=GITLAB), \
                    patch.object(f, "gitlab_mr_rows", return_value=(rows, "" if rows is not None else failure)) as listed, \
                    patch.object(f.subprocess, "run", side_effect=AssertionError("gh must not run")):
                state = f.judge_route_state({}, "fn-1-feature")
            self.assertEqual(listed.call_args.kwargs["head"], "fn-1-feature")
            return f.judge_route(state)

    def test_gitlab_mrs_route_like_prs(self):
        open_row = f._gitlab_mr_row(mr(3))
        merged_row = f._gitlab_mr_row(mr(2, "merged"))
        self.assertEqual(self.state([open_row])["decision"]["value"], "existing_pr_tail")
        self.assertEqual(self.state([merged_row])["decision"]["value"], "existing_pr_tail")
        self.assertEqual(self.state([])["decision"]["value"], "all_done_make_pr")
        self.assertTrue(self.state(None)["pr_probe_failed"])

    def test_missing_glab_is_a_probe_failure_never_no_mr(self):
        with patch.object(f.subprocess, "run", side_effect=FileNotFoundError("glab")):
            rows, failure = f.gitlab_mr_rows(Path("."), GITLAB, head="x")
        self.assertIsNone(rows)
        self.assertIn("glab unreachable", failure)
        self.assertTrue(self.state(None, "glab unreachable: not found")["pr_probe_failed"])


class PlainOutputTests(unittest.TestCase):
    """Shell callers compare `$(flowctl forge detect)`; a Windows CR would never match."""

    def test_detect_prints_lf_only_through_a_pipe(self):
        result = subprocess.run([sys.executable, str(SCRIPTS / "flowctl.py"), "forge", "detect"],
                                cwd=SCRIPTS, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(b"\r", result.stdout)
        self.assertTrue(result.stdout.endswith(b"\n"))

    def test_empty_head_is_refused_not_listed_unfiltered(self):
        out = io.StringIO()
        with patch.object(f, "detect_forge", side_effect=AssertionError("no lookup")), redirect_stdout(out), \
                self.assertRaises(SystemExit):
            f.cmd_forge_mr_list(SimpleNamespace(head="", number=None, state="open", limit=100, json=True))
        self.assertIn("--head names no branch", out.getvalue())


class MrWriteTests(unittest.TestCase):
    def run_cmd(self, func, args, response, returncode=0):
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs.get("input")))
            return done(json.dumps(response), returncode=returncode,
                        stderr='Source branch "x" does not exist (HTTP 422)' if returncode else "")
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            body = Path(tmp) / "body.md"
            body.write_text("Grounded body \u2014 unicode\n", encoding="utf-8")
            with patch.object(f, "detect_forge", return_value=GITLAB), patch.object(f, "get_repo_root", return_value=Path(tmp)), \
                    patch.object(f.subprocess, "run", side_effect=run), redirect_stdout(out):
                try:
                    func(SimpleNamespace(body_file=str(body), **args))
                    code = 0
                except SystemExit as exc:
                    code = exc.code
        return code, out.getvalue(), calls

    def test_create_posts_the_body_and_prints_the_url(self):
        code, out, calls = self.run_cmd(f.cmd_forge_mr_create,
                                        {"title": "Title", "base": "main", "head": "fn-1", "draft": True}, mr(12))
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "https://gitlab.example.com/group/sub/proj/-/merge_requests/12")
        argv, sent = calls[0]
        self.assertIn("POST", argv)
        self.assertIn("Content-Type: application/json", argv)
        self.assertEqual(json.loads(sent), {"source_branch": "fn-1", "target_branch": "main", "title": "Draft: Title",
                                            "description": "Grounded body \u2014 unicode\n"})

    def test_create_failure_reports_glabs_error(self):
        stderr = io.StringIO()
        with patch.object(f.sys, "stderr", stderr):
            code, _, _ = self.run_cmd(f.cmd_forge_mr_create,
                                      {"title": "T", "base": "main", "head": "x", "draft": False}, {}, returncode=1)
        self.assertEqual(code, 1)
        self.assertIn('Source branch "x" does not exist', stderr.getvalue())

    def test_update_replaces_the_description(self):
        code, out, calls = self.run_cmd(f.cmd_forge_mr_update, {"number": 11}, mr(11))
        self.assertEqual(code, 0)
        self.assertTrue(out.strip().endswith("/merge_requests/11"))
        argv, sent = calls[0]
        self.assertIn("PUT", argv)
        self.assertTrue(argv[-1].endswith("merge_requests/11"))
        self.assertEqual(json.loads(sent), {"description": "Grounded body \u2014 unicode\n"})


if __name__ == "__main__":
    unittest.main()
