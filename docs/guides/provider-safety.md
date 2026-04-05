# Provider usage and safety

Sponte calls **external harness CLIs** that may use network APIs subject to billing, rate limits, and provider policy. Sponte cannot guarantee protection from bans, unexpected charges, or enforcement actions.

## Practical habits

- Prefer **conservative** model and automation settings until you trust the loop.
- Avoid **on-demand spending** unless you intentionally accept that tradeoff.
- Review **git diffs** and harness logs before merging to trunk.
- Treat `review-required` as a pause for human judgment, not noise.

## Honest expectations

Wrapping official CLIs helps Sponte stay compatible with upstream changes and subscriptions, but it does not remove provider risk. If something looks wrong, stop the session and fix workspace or policy before resuming.
