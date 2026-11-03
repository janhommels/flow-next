"""make-pr preflight auth check must not assume github.com (#532)."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make-pr-preflight.sh"
FLOWCTL = SCRIPT.parent / "flowctl"


@unittest.skipIf(os.name == "nt" or not shutil.which("bash") or not shutil.which("jq"), "POSIX stubs and jq")
class PreflightAuthTests(unittest.TestCase):
    def run_auth_block(self, gh_body, origin="https://github.com/o/r.git", upstream=None, ssh_body=None,
                       glab_body="exit 1"):
        with tempfile.TemporaryDirectory() as temp:
            bin_dir = Path(temp) / "bin"
            bin_dir.mkdir()
            for name, body in (("gh", gh_body), ("ssh", ssh_body), ("glab", glab_body)):
                if body is not None:
                    stub = bin_dir / name
                    stub.write_text("#!/usr/bin/env bash\n" + body + "\n")
                    stub.chmod(0o755)
            block = SCRIPT.read_text(encoding="utf-8").split("# end:block", 1)[0]
            env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"], DRY_RUN="0",
                       REPO_ROOT=temp, FLOWCTL=str(FLOWCTL))
            subprocess.run(["git", "init", "-q", temp], check=True)
            subprocess.run(["git", "-C", temp, "remote", "add", "origin", origin], check=True)
            if upstream:
                subprocess.run(["git", "-C", temp, "remote", "add", "upstream", upstream], check=True)
            return subprocess.run(["bash", "-c", block], env=env, capture_output=True, text=True)

    def test_enterprise_only_login_passes(self):
        # Logged in to a GHE host only: a github.com-scoped check fails, a plain one passes.
        result = self.run_auth_block('[[ "$*" == *"--hostname github.com"* ]] && exit 1; exit 0')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_valid_github_com_with_expired_other_host_passes(self):
        # Valid github.com login plus an expired login elsewhere: the all-hosts check fails, github.com passes.
        result = self.run_auth_block('[[ "$*" == *"--hostname github.com"* ]] && exit 0; exit 1')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unauthenticated_stops_without_naming_github_com(self):
        result = self.run_auth_block("exit 1")
        self.assertEqual(result.returncode, 1)
        self.assertIn("gh auth status", result.stderr)
        self.assertNotIn("github.com.", result.stderr)


    # #583: a non-GitHub origin stops before any close or push, logged in or not,
    # and whatever other remotes the repository has.
    NO_TOKEN = '[[ "$1 $2" == "auth token" ]] && exit 1; exit 0'

    def test_unknown_origin_stops_as_needs_human_naming_both_clis(self):
        for gh_body in (self.NO_TOKEN, "exit 4"):  # logged in elsewhere, or not at all
            with self.subTest(gh_body=gh_body):
                result = self.run_auth_block(
                    gh_body, origin="https://user:secret-token@git.example.com/group/proj.git")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("NEEDS_HUMAN: make-pr opens GitHub pull requests and GitLab merge requests only",
                              result.stderr)
                self.assertIn("gh auth login --hostname git.example.com", result.stderr)
                self.assertIn("glab auth login --hostname git.example.com", result.stderr)
                self.assertNotIn("secret-token", result.stderr)

    def test_github_upstream_beside_an_unknown_origin_still_stops(self):
        result = self.run_auth_block(self.NO_TOKEN, origin="git@git.example.com:group/proj.git",
                                     upstream="https://github.com/o/r.git")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("git.example.com", result.stderr)

    GLAB_HOST_OK = '[[ "$1 $2 $3 $4" == "auth status --hostname gitlab.example.com" ]] && exit 0; exit 1'

    def test_self_managed_gitlab_origin_glab_is_logged_in_to_passes(self):
        for origin in ("https://gitlab.example.com/group/sub/proj.git", "git@gitlab.example.com:group/proj.git"):
            with self.subTest(origin=origin):
                result = self.run_auth_block(self.NO_TOKEN, origin=origin, glab_body=self.GLAB_HOST_OK)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_gitlab_com_origin_without_glab_login_names_the_fix(self):
        result = self.run_auth_block(self.NO_TOKEN, origin="https://gitlab.com/group/proj.git")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("glab auth login --hostname gitlab.com", result.stderr)

    def test_gitlab_com_origin_with_glab_login_passes(self):
        result = self.run_auth_block("exit 1", origin="https://gitlab.com/group/proj.git", glab_body="exit 0")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_enterprise_origin_with_a_gh_token_passes(self):
        result = self.run_auth_block(
            '[[ "$1 $2 $3 $4" == "auth token --hostname ghe.corp" ]] && exit 0; '
            '[[ "$1 $2" == "auth token" ]] && exit 1; exit 0',
            origin="https://ghe.corp/o/r.git")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_userless_scp_alias_resolving_to_github_passes(self):
        # host:path takes its user from ssh config; the alias still resolves through ssh -G.
        result = self.run_auth_block(
            self.NO_TOKEN, origin="gh-work:o/r.git",
            ssh_body='[[ "$1 $2" == "-G gh-work" ]] && echo "hostname github.com"; exit 0')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
