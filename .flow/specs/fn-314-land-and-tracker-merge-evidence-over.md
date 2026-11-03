# land and tracker merge evidence over GitLab merge requests

## Goal & Context

`land` resolves feedback and CI for one GitHub pull request and squash merges it with `gh pr merge --squash --match-head-commit`; every step names GitHub concepts (checks, `reviewDecision`, update-branch, merge queue). Tracker sync moves an issue to terminal Done only on merge evidence, and that evidence is read from GitHub PRs only, so on a GitLab-hosted repo a tracker never reaches Done even after the MR merged (issue #462). [paraphrase]

land is already pure skill prose with no scripts, so on GitLab the agent can drive `glab` from a short GitLab section, the way resolve-pr does in its sibling spec. What must not be left to improvisation are the merge rails, which this spec states as criteria, and the tracker merge evidence, which is deterministic Python and needs a code change. GitHub behaviour stays exactly as it is. [paraphrase]

<!-- Source: 20% user / 60% [paraphrase] (user, issue #462, former fn-73 stub) / 20% [inferred] -->

## Architecture & Data Models

- **land: guidance plus rails.** One GitLab section in land maps each gate to its GitLab signal (head pipeline for CI, approvals and unresolved discussions for review, the MR's detailed merge status for mergeability, rebase for catch-up) and states the rails below. No new scripts, flowctl verbs or config keys. [paraphrase]
- **Merge evidence: code.** The tracker merge-evidence probe reads the spec branch's MRs on a GitLab origin with the outcomes it has for PRs (merged, open, closed-unmerged, none, ambiguous, probe error) and the same rule that a merge touching only `.flow/` spec files is not evidence. Terminal Done stays gated on a genuinely merged PR or MR. Forge from the shared detection of the ship-loop sibling spec. [paraphrase]

## Edge Cases & Constraints

- Self-managed GitLab is first-class. [paraphrase]
- GitLab pipeline states are wider than GitHub checks (`manual`, `skipped`, `canceled`, no pipeline); approvals may be optional, required or unreadable. [paraphrase]
- Merge trains, merge queues and native stacks have no counterpart here. [inferred]

## Acceptance Criteria

- **R1:** On a GitLab origin, `land <MR>` with current consent squash merges the MR via `glab` once its head pipeline is green, its discussions are resolved and it is mergeable, and emits `LAND_VERDICT=MERGED` with the MR URL and merge commit. Errors: `glab` absent or not authenticated → clear message, no merge; pipeline failed → the bounded CI-fix path, then a non-merged verdict; not mergeable → a non-merged verdict naming the status. [paraphrase]
- **R2:** land merges only the head SHA it verified: a head that moved after verification aborts the merge with a non-merged verdict. Errors: no error surface beyond that stop. [paraphrase]
- **R3:** land never enables GitLab auto-merge ("merge when pipeline succeeds"). Errors: no error surface beyond R1. [paraphrase]
- **R4:** A pending, manual, skipped, canceled, absent or unknown pipeline, and required-but-missing or unreadable approvals, never lead to a merge. Errors: each ends in a non-merged verdict naming the state. [paraphrase]
- **R5:** Tracker merge evidence on a GitLab origin reports `merged` for a spec branch whose MR merged with code changes, so lifecycle sync and land's post-merge tail move the issue to terminal Done; a spec-only merge is not evidence. Errors: `glab` failure → probe error, never terminal Done. [paraphrase]
- **R6:** GitHub repos behave byte-for-byte as before in land and merge evidence. Errors: no error surface beyond today's. [paraphrase]

## Boundaries

- No new scripts, flowctl verbs or config keys for land. [paraphrase]
- Only the `glab` CLI; no REST fallback. [paraphrase]
- Merge trains and fork-sourced MRs are out of scope. [inferred]

## Decision Context

Third of three specs from one effort (GitLab as a forge next to GitHub, issue #462, superseding the fn-73 stub): (A) GitLab MRs in the ship loop, (B) resolve-pr over MR discussions, and (C) this spec, depending on A and B because land delegates review convergence to resolve-pr. A first draft specified land's GitLab behaviour gate by gate; it was cut to one guidance section plus the merge rails as criteria, following the repo's agent-first principle, which keeps deterministic machinery for unattended-trust rails. Forge detection from the origin remote and `glab`-only transport are recorded in A. [paraphrase]

## Strategy Alignment

- Machinery only where the strategy reserves it: merge rails and merge evidence are unattended-trust rails; the rest is guidance. [strategy:Design principles]
