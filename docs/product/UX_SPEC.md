# UX Specification

**Status:** observed with deferred states  
**Confidence:** 88/100

## Comprehension contract

Within ten seconds, the user should understand:

1. DriftGuard prevents important work from quietly drifting.
2. The user defines what must remain true.
3. DriftGuard checks an action or output.
4. The user receives Pass, Watch, or Block and the smallest correction.

Within sixty seconds, a first-time user should be able to complete the four required intent fields and generate or manually create guardrails.

## Primary path

1. **Intent:** four required plain-language fields.
2. **Constraints:** review and edit guardrails; advanced policy controls remain collapsed by default.
3. **Judgment:** submit work and only the evidence demanded by active rules.
4. **Result:** verdict first, highest-priority issue second, smallest correction third, full trace last.

## Current interface states

| State                     | Required behavior                                                                         |
| ------------------------- | ----------------------------------------------------------------------------------------- |
| First use / empty         | Provide a realistic editable sample without claiming it is the user's data.               |
| Loading                   | Disable duplicate action and show the exact active operation.                             |
| Success                   | Show verdict and next action before score or implementation metadata.                     |
| Missing data              | Name the missing field or evidence value.                                                 |
| Low confidence            | Return Watch; never visually imply Pass.                                                  |
| Validation error          | Preserve entered state and give one correction.                                           |
| External provider failure | Preserve work and state that no cloud judgment was completed.                             |
| Permission failure        | Prompt sign-in without deleting the local workspace.                                      |
| Timeout                   | Explain that the provider timed out and allow retry.                                      |
| Resumed workflow          | Reload the latest owned workspace after sign-in.                                          |
| Historical result         | Persisted in the database; dedicated history UI is deferred until repeat use is observed. |
| Comparison view           | Deferred until users demonstrate a repeated need to compare versions or checks.           |

## Acceptance metrics

```yaml
comprehension_time_target_seconds: 10
time_to_first_value_target_seconds: 60
input_error_rate_target: < 10%
first-check_completion_target: > 70%
recoverable_failure_recovery_target: > 80%
repeat_use_target_14_days: > 30%
correction_acceptance_target: > 40%
support_requests_target: < 0.2 per active user per month
```
