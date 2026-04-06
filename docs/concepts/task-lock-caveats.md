# Task lock file caveats (`tasks.lock`)

Sponte may record **locked task files** in `.sponte/locks/tasks.lock` using **absolute paths** to the task markdown on disk.

That choice is intentional (clear identity, easy to read in logs and terminals) but has operational caveats.

## Paths are tied to one checkout layout

The same git commit checked out in two places usually has **different absolute paths**:

- Different machines (e.g. `/Users/alice/proj` vs `/home/bob/proj`).
- Multiple local clones (`…/sponte` vs `…/sponte-work`).
- CI jobs with a **new workspace root every run**.

A `tasks.lock` produced on machine A can list paths that **do not exist** on machine B. Sponte may treat those entries as stale, or they may block logic until cleaned up.

## Symlinks and OS normalization

macOS and some tools expose paths with different spellings (e.g. `/var` vs `/private/var`). Opening the repo via a symlink can change the prefix of absolutes. Two sessions resolving the “same” file might disagree on the string form unless the implementation normalizes consistently.

## Committing vs gitignoring `tasks.lock`

If `tasks.lock` is **committed**, teammates pull **your machine’s** absolute paths into their trees—usually **wrong** for them. Typical pattern: **gitignore** `.sponte/locks/tasks.lock` (or the whole locks dir) so locks stay **local ephemeral** state, unless you have a single shared absolute layout (rare).

## Operational mitigations

- Prefer **one primary clone path** per workspace when using shared docs that reference lock paths.
- After moving or renaming a repo directory, **clear or regenerate** `tasks.lock` if behavior looks stuck.
- For automation, rely on **session** ids and **repo-relative** task paths when you need the same logical task across clones; treat absolutes in `tasks.lock` as **runtime bookkeeping**, not a portable identifier across clones.

## `task_id` derived from absolute path (planned)

If Sponte derives **`task_id`** from the resolved **absolute path** of the task file (e.g. hash of `Path.resolve()`), then the same markdown at `.sponte/tasks/foo.md` in two clones gets **two different** `task_id` values, because the absolute prefixes differ. That is consistent with absolute entries in `tasks.lock` but means **`.sponte/jobs/tasks/<task_id>/`** metadata does not transfer between machines by id alone—use **relative path** or **human-facing names** (e.g. AI-generated display title in `status.json`) when communicating about a task across checkouts.

Related: [tasks and sessions](tasks-and-sessions.md), [session and task ownership](session-task-ownership.md).
