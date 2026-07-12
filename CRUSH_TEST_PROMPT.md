# TraceCrumb crush test

Use this script with real incident responders. Do not explain the intended answer before the test.

## Participant

A person who has recently participated in a software incident and can use fully redacted information.

## Setup

Send a source-tagged URL:

```text
https://YOUR_DOMAIN/?source_channel=crush_test
```

Ask the participant to use a real, redacted incident theory or the worked example if policy prevents real input.

## Tasks

1. After ten seconds on the landing page, ask:
   - What does this product do?
   - When would you use it?
   - What will happen after you click the main button?

2. Ask the participant to run one check without guidance.

3. After the result, ask:
   - What signal did the review say does not fit?
   - What alternative explanation did it suggest?
   - What is the cheapest falsification check?
   - Would this change, stop, or confirm the next action?

4. Ask the participant to record the next move.

5. Ask whether they would:
   - save the record;
   - use it during another incident;
   - pilot it with their team;
   - pay for an assisted or team version.

## Pass conditions

The session passes when all are true:

- the participant explains the product and trigger correctly after ten seconds;
- they reach a saved review without operator assistance;
- the output references their incident rather than generic advice;
- they can identify the mismatch and falsification check;
- they record a next move;
- no output is mistaken for verified root cause;
- the system stores `first_value_reached` and the source channel.

## Strong demand evidence

Count separately:

- review marked useful;
- review would change the next action;
- email linked after first value;
- second incident reviewed by the same user;
- team pilot requested;
- payment, deposit, or signed pilot commitment.

Do not count a page view, anonymous click, or worked-example view as product demand.

## Failure conditions

- user cannot explain the purpose;
- account is requested before result;
- output is generic or ignores supplied evidence;
- output presents hypothesis as fact;
- provider error destroys the saved decision;
- user cannot distinguish original theory from generated review;
- next move and outcome cannot be recorded;
- source attribution is lost.
