# TraceCrumb Wedge Specification

## Wedge

TraceCrumb is a first-theory checkpoint for software incidents. It preserves the first operational theory before review, surfaces the strongest contradiction, a credible alternative, the cheapest falsification check, and the boundary that should force a switch.

## Inelastic pain

During an incident, the first plausible explanation often becomes the plan before the team records what contradicts it. The cost is not “bad reasoning” in the abstract; it is expensive time spent rolling back, restarting, escalating, or investigating the wrong branch.

## Validation user

SRE, platform, reliability, and incident-response practitioners with a live decision, a real consequence, and authority or influence over the next move.

## Active access model

- Email-only validation signup.
- No account/authentication system.
- One random browser token per workspace.
- Ten server-enforced live runs per email/browser workspace.
- Same-browser history only during validation; export is the portability mechanism.

## Mechanism contract

Input must distinguish:

1. directly observed state;
2. current theory;
3. directly observed evidence;
4. assumptions;
5. signals that do not fit;
6. known unknowns;
7. consequence if wrong;
8. action about to be taken;
9. condition that forces a switch.

Output must show exactly four primary cards:

1. strongest contradiction;
2. credible alternative cause;
3. cheapest falsification check;
4. decision boundary.

## Evidence contract

The wedge is supported only when real use produces:

- a qualified decision submission;
- an explicit post-review move;
- a credible and executable check;
- a recorded effect on decision, test, timing, participants, or confidence;
- an eventual outcome;
- repeat use or evidence sharing.

A page view, worked example, signup, or generic “helpful” response is not proof.

## Non-goals

TraceCrumb does not claim root cause, query live telemetry, execute remediation, score responders, replace incident command, or provide a durable multi-user account system during this validation stage.
