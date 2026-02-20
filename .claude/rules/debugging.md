---
description: Systematic debugging methodology using Prediction Protocol
always_apply: true
---
## Prediction Protocol (mandatory for debugging)

When encountering a bug or unexpected behavior, ALWAYS follow this sequence:

1. **PREDICT** — Before investigating, state your hypothesis:
   - What do you expect the current behavior to be?
   - What is the expected correct behavior?
   - Where do you think the issue originates?

2. **OBSERVE** — Gather evidence (never skip this):
   - Read the actual error message/output
   - Check logs, stack traces, console output
   - Reproduce the issue with minimal steps

3. **COMPARE** — Explicitly compare prediction vs observation:
   - Where did your prediction match reality?
   - Where did it diverge?
   - What does the divergence tell you?

4. **EXPLAIN** — Form a root cause explanation:
   - Why did the divergence happen?
   - Is this a symptom of a deeper issue?
   - What is the minimal fix?

5. **VERIFY** — Confirm the fix:
   - Does the fix address root cause (not just symptom)?
   - Run relevant tests
   - Check for regressions in related functionality

## Anti-patterns (NEVER do)
- Shotgun debugging: changing multiple things at once without hypotheses
- Assuming the fix worked without verification
- Ignoring test failures as "flaky" without investigation
- Skipping reproduction: "it works on my machine"
- Deep-diving without checking docs/LESSONS-LEARNED.md for similar past incidents
