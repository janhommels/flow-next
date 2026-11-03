# Defect route: bisect (gated reference)

> Read from defect-route.md step 3 only when the report or the history names a known-good revision.

When the report or the history names a revision where the behaviour was correct (a tag, a release, "it worked last week"), bisect with the reproduction as the test: a script outside the repository that exits `0` on good, `1` on bad and `125` when a revision cannot be tested.

```bash
git worktree add --detach <tmp-dir> <bad-rev>
git -C <tmp-dir> bisect start <bad-rev> <good-rev>
git -C <tmp-dir> bisect run <script>
git -C <tmp-dir> bisect reset
git worktree remove <tmp-dir>
```

Read the introducing commit and the pull request that carried it (`gh pr list --state merged --search <sha>`; on a GitLab origin,
`glab api "projects/:id/repository/commits/<sha>/merge_requests"`, keeping those whose
`state` is `merged`). A lookup that fails is recorded
as unchecked, not a stop. Its intent feeds the fix design, and the commit is cited in the diagnosis.

Skip this step, and record why, when there is no known-good revision, no bisectable history (a new repository, a squashed import, a shallow clone), or no reproduction cheap enough to run once per revision.
