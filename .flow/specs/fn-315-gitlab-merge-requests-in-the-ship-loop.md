# GitLab merge requests in the ship loop: forge detection, make-pr and flow --auto

## Goal & Context

GitLab is a supported tracker but not a supported forge. `make-pr` opens pull requests only through `gh`, and on a non-GitHub origin it now stops with `NEEDS_HUMAN` before closing the spec or pushing (#583, fn-310). A GitLab-hosted repo therefore never gets the PR-as-cognitive-aid body, and `flow --auto` ends at the PR boundary. Upstream issue #462 asks for this, and a GitLab user has offered to test a branch on a GitLab repo. [paraphrase]

This spec is the first of three. It makes the ship loop reach an open GitLab merge request (MR): flow-next tells from the repository which forge hosts the code, `make-pr` opens or updates an MR through the `glab` CLI, and the route probe and the PR tail of `flow --auto` see that MR. Sibling specs cover `resolve-pr` on MR discussions and `land` plus tracker merge evidence on MRs; both depend on the detection defined here. GitHub behaviour stays exactly as it is. [paraphrase]

<!-- Source: 10% user / 60% [paraphrase] (user request, issue #462, fn-310) / 30% [inferred] -->

## Architecture & Data Models

- **Forge is a property of the checkout, observed per run.** The forge (GitHub or GitLab) and its host come from the `origin` remote: its host (with SSH aliases resolved, as make-pr already does) is GitHub when it is github.com or a host `gh` is logged in to, and GitLab when it is gitlab.com or a host `glab` is logged in to. Nothing is persisted and no config key is added. The tracker axis (`tracker.type`) stays independent: GitLab issues with GitHub PRs, or the reverse, keep working. [paraphrase]
- **One detection, every consumer.** The shell side of make-pr and the Python route/pilot probes must agree on the forge; they use one detection rule, not two that can drift. Where it lives is the implementer's call. [inferred]
- **Neutral MR facts.** Consumers need the same few facts from either forge: number (GitLab `iid`), URL, state (open / merged / closed), head SHA, source and target branch, draft. GitLab's `opened` / `locked` map onto open; anything else is not open. Existing GitHub field names in receipts and snapshot output stay as they are. [inferred]
- **Body rendering is forge-neutral already.** The cognitive-aid export and render are reused unchanged; only the transport underneath changes. [paraphrase]
- **Reuse existing `glab` knowledge.** The tracker package already works around measured `glab` defects (the "Multiple config files found" warning printed to stdout ahead of JSON, `--hostname` needing a bare host without scheme or port). The forge path reuses those fixes rather than rediscovering them. [paraphrase]

## API Contracts

- **make-pr on a GitLab origin:** pushes the branch, then creates the MR with title, rendered body, source branch, target branch (`--base` or the default branch) and draft flag; under `--update`, replaces the open MR's description. Prints the MR URL (`https://<host>/<group>/<project>/-/merge_requests/<iid>`) where it prints the PR URL today; resolve-pr and dry-run pointers print as before. [inferred]
- **`FLOW_PR_CREATE_CMD`** keeps its contract (output must contain the created URL); a GitLab MR URL is an accepted URL shape alongside GitHub's `/pull/<n>` and Bitbucket's `/pull-requests/<n>`. [inferred]
- **Route and pilot probes on a GitLab origin** report MRs in the same output fields they report PRs in today (`pr_exists`, `pr_probe_failed`, `pr.open` / `merged` / `closed`, `current_branch_prs`). [inferred]

## Edge Cases & Constraints

- **Self-managed GitLab is first-class.** Never assume gitlab.com; the host comes from the remote. [paraphrase]
- `glab` missing, or not logged in for the origin host: make-pr stops with a clear message naming the host and `glab auth login --hostname <host>`, before any close commit or push. Under `mode:autonomous` this is a hard error, as today's gh failures are. [paraphrase]
- Origin host that neither `gh` nor `glab` recognises (Bitbucket, Gitea, an unknown host): today's `NEEDS_HUMAN` stop stays, reworded to name both CLIs. [inferred]
- A GitLab chain parent (dependency spec's branch) is found by source branch with its state and target branch; a merged parent's history is recovered from GitLab's MR head ref, not GitHub's `refs/pull/<n>/head`. [inferred]
- GitHub native stacks have no GitLab equivalent: stack linking and the Stack line are skipped on GitLab, silently and without failing the run. [inferred]
- The create retry recognises GitLab's eventual-consistency errors; other create failures fail as today. [inferred]
- GitLab returns at most one open MR per source branch per project; an MR from a fork is out of scope (see Boundaries). [inferred]

## Acceptance Criteria

- **R1:** On a repo whose origin is GitLab (gitlab.com or a self-managed host `glab` is logged in to), `make-pr <spec-id>` opens a merge request with the rendered body via `glab`, closing the spec first exactly as it does for GitHub, and prints the MR URL. Errors: `glab` absent or not authenticated for the host → clear message naming the fix, exit before any close commit or push; create failure after push → non-zero exit with glab's error, spec close commit kept as on GitHub. [paraphrase]
- **R2:** On a GitLab origin, `make-pr --update` replaces the open MR's description, `--draft` / `--ready` and `--base` take effect on the MR, and an existing open MR without `--update` is refused as an open PR is today. Errors: `--update` with no open MR → the same refusal GitHub gets. [inferred]
- **R3:** On a GitLab origin, chain detection finds a dependency spec's MR by its source branch, honours its state and target branch, and recovers a merged parent's history; stack linking is skipped. Errors: MR lookup fails → `NEEDS_HUMAN` on a real run, as the GitHub lookup failure does. [inferred]
- **R4:** The forge is detected from the `origin` remote with no new config key, and GitHub repos (github.com and GitHub Enterprise) behave byte-for-byte as before: same commands, same output, same exit codes. Errors: an origin neither CLI recognises keeps a `NEEDS_HUMAN` stop that names both `gh` and `glab`. [paraphrase]
- **R5:** `flowctl judge --preset route` and the `flow --auto` pilot snapshot list GitLab MRs for the spec branch: an open or merged MR routes to the existing-PR tail, no MR routes to make-pr, and a GitLab origin is no longer classed as "no PR forge". Errors: `glab` failure → `pr_probe_failed: true` / `probe_failed`, never a silent "no MR". [paraphrase]
- **R6:** After make-pr, `flow --auto` verifies the MR exists, and the flow tail binds and observes it (URL, state, head SHA, merge commit) on a GitLab origin as it does a GitHub PR. Errors: verification probe failure → the same crash-class `NEEDS_HUMAN` GitHub gets. [paraphrase]
- **R7:** The no-spec make-pr path and the features chore-PR path open an MR on a GitLab origin. Errors: as R1. [inferred]
- **R8:** why-scout and the defect route's prior-fix search look up merged MRs on a GitLab origin where they look up merged PRs on GitHub. Errors: lookup failure is reported as missing evidence, not an error stop. [inferred]

## Boundaries

- GitHub behaviour does not change. [paraphrase]
- Only the `glab` CLI is a transport; no REST fallback with `GITLAB_TOKEN` / `CI_JOB_TOKEN`. This matches the GitHub side, which needs `gh` with no REST fallback; headless runs use `glab` with `GITLAB_TOKEN`. [paraphrase]
- No new config key for the forge. [paraphrase]
- MRs from forks, GitLab merge trains, and other forges (Bitbucket, Gitea) are out of scope. [inferred]
- `spec.approval=pr` (readiness from PR approval) and prime's GitHub settings scan stay GitHub-only. [inferred]
- `resolve-pr`, `land` and tracker merge evidence on MRs belong to the two sibling specs. [paraphrase]

## Decision Context

Split from one effort into three specs at capture: (A) this spec, (B) `resolve-pr` over MR discussions, depending on A, and (C) `land` plus tracker merge evidence over GitLab MRs, depending on A and B. A ships value alone: a GitLab team gets the cognitive-aid MR and an `flow --auto` run that ends at an open MR. [paraphrase]

Forge selection reads the origin remote rather than adding the `forge.type` config axis #462 proposes: the forge is observable on every run, and the repo's agent-first rule (G4) asks a new required key to name the failure it prevents. A mirror whose origin is not the review forge is the case this gives up; it can be revisited when someone hits it. Transport is `glab` only, matching the request and the `gh`-only GitHub side; #462's REST fallback for headless CI is left out. This spec supersedes the fn-73 stub (glab git-ops over GitLab merge requests), which planned a general forge-adapter layer resolved once and persisted; reading the forge from the remote makes the persisted resolution unnecessary. [paraphrase]

## Strategy Alignment

- The Cross-platform parity track is about host agents; #462 argues the forge is the remaining axis where one vendor is a hard dependency, and this spec removes that dependency for the ship loop's first half. [strategy:Cross-platform parity]
