# Provider and local safety

Sponte drives **native/official harness CLIs**. It is not a provider-bypass layer and does not replace upstream agent runtimes. You should still expect normal provider billing, rate limits, authentication, and policy enforcement from whichever CLI you run.

The bigger operational risk is local execution. Sponte is designed for permissive development workflows and does **not** sandbox agent commands, file access, network access, secrets, or production resources. Run it only in development workspaces where you are comfortable giving the selected harness full command permissions. Do **not** run it against production environments or production credentials.

## Practical habits

- Prefer **conservative** model and automation settings until you trust the loop.
- Avoid **on-demand spending** unless you intentionally accept that tradeoff.
- Start in a disposable or development checkout before trusting a long-running loop.
- Review **git diffs** and harness logs before merging to trunk.
- Treat `review-required` as a pause for human judgment, not noise.

## Honest expectations

Wrapping official CLIs helps Sponte stay compatible with upstream changes, subscriptions, and provider expectations, but it does not remove billing, policy, or local execution risk. If something looks wrong, stop the session and fix the workspace, credentials, or policy before resuming.
