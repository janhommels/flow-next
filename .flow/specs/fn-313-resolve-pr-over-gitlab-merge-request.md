# resolve-pr over GitLab merge request discussions

## Goal & Context

`resolve-pr` reads, answers and resolves review feedback through GitHub only: its preflight requires `gh auth status`, its helper scripts use GitHub GraphQL review threads, its target parsing accepts only `github.com/.../pull/<n>` URLs, and its push target is built as a github.com URL. On a GitLab-hosted repo nothing in the skill tells the agent what to do, so whether MR feedback gets handled depends on the agent improvising (issue #462). [paraphrase]

The user has run resolve-pr on a GitLab project without noticing problems, which suggests a capable agent already bridges the gap with `glab` on its own. This spec therefore makes that path explicit and safe with a few sentences of guidance, not a parallel GitLab implementation: the GitHub-only assumptions apply only on GitHub origins, and the skill states what must hold on GitLab. GitHub behaviour stays exactly as it is. [paraphrase]

<!-- Source: 20% user / 60% [paraphrase] (user, issue #462, review of the skill) / 20% [inferred] -->

## Architecture & Data Models

- **Guidance, not machinery.** On a GitLab origin the agent drives `glab` itself, guided by a short GitLab section in the skill. No new helper scripts, no GitLab GraphQL port, no new flowctl verb or config key. The existing GitHub scripts stay GitHub-only. [paraphrase]
- **Forge from the shared detection** of the ship-loop sibling spec (origin remote). [paraphrase]
- **MR discussions are the unit.** A resolvable MR discussion plays the role of a GitHub review thread; a non-resolvable MR note plays the role of a top-level comment. MR discussions and issue notes are different things and are never conflated. The per-thread resolver contract (one thread in, same verdicts out) stays. [paraphrase]

## Edge Cases & Constraints

- Self-managed GitLab is first-class; the host comes from the remote. [paraphrase]
- System notes (pushes, label changes) are never feedback. [inferred]
- Fork-sourced MRs are out of scope; resolve-pr says so instead of pushing elsewhere. [inferred]

## Acceptance Criteria

- **R1:** On a GitLab origin, resolve-pr does not stop on its GitHub preflight or GitHub-only target parsing: it accepts no argument (the current branch's open MR), an MR number or an MR URL, and pushes fixes to the MR's source branch on the origin. Errors: `glab` absent or not authenticated for the host → clear message naming `glab auth login --hostname <host>`, nothing changed; no open MR for the branch → the same message the GitHub no-PR case gives. [paraphrase]
- **R2:** On a GitLab origin, resolve-pr considers every unresolved resolvable discussion and every non-system top-level note of the MR (all pages; a truncated listing is reported, never silent), replies in each discussion it handled and resolves only those, and answers top-level notes without resolving anything. Errors: a resolve the forge refuses (permission, already resolved) is reported for that discussion and the rest continue. [paraphrase]
- **R3:** GitHub repos behave byte-for-byte as before. Errors: no error surface beyond today's. [paraphrase]

## Boundaries

- No new scripts, flowctl verbs or config keys for GitLab. [paraphrase]
- Only the `glab` CLI; no REST fallback. [paraphrase]
- MR approvals, pipelines and merging belong to the land sibling spec. [inferred]

## Decision Context

Second of three specs from one effort (GitLab as a forge next to GitHub, issue #462, superseding the fn-73 stub): (A) GitLab MRs in the ship loop (forge detection, make-pr, flow --auto), (B) this spec, depending on A, and (C) land plus tracker merge evidence over GitLab MRs. A first draft of this spec ported the four GraphQL helper scripts to GitLab; it was cut to guidance after the user reported the skill already coped with GitLab, following the repo's agent-first and bitter-lesson principles. Forge detection from the origin remote and `glab`-only transport are recorded in A. [paraphrase]

## Strategy Alignment

- Applies the Agent-first principle: the agent decides how to drive `glab`; the skill states only what must hold. [strategy:Design principles]
