# Primary checkout: unfinished merge before Ralph merge

The **primary** repository checkout (not the task worktree) is in a **git merge** conflict state **before** Ralph merges the feature branch into the default branch.

Resolve conflicts using your best judgment: preserve others' work, keep behavior correct, run targeted checks if helpful.

When done, `git add` all resolved files and complete the merge (e.g. `git commit` if the merge is not finished). **Do not** `git push`. **Do not** run `git merge --abort` unless you intend to discard this merge entirely.
