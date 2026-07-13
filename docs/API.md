# Evaluation API

DriftGuard's workflow integration boundary is the authenticated Supabase Edge Function. It is suitable for a browser, internal tool, automation, or webhook relay that already has a DriftGuard user's Supabase access token.

## Canonical function registry

The public endpoint slugs are the literal folders `evaluate` and `infer-guardrails`. `npm run check:edge` rejects mismatches between those folders, `supabase/config.toml`, and browser invocation constants. The aggregate deploy command supplies no function names, while each diagnostic command supplies one literal name. This keeps the public slugs unambiguous across deployment surfaces.

## Endpoint

```text
POST https://PROJECT_REF.supabase.co/functions/v1/evaluate
```

## Headers

```http
Authorization: Bearer USER_ACCESS_TOKEN
apikey: sb_publishable_YOUR_KEY
Content-Type: application/json
```

The publishable key identifies the Supabase project. The bearer token identifies the user. The function independently verifies the bearer token and rejects anonymous calls.

## Body

```json
{
  "workspace": {
    "id": "set_UUID",
    "name": "Release guardrails",
    "purpose": "Ship a credible release without unsupported claims",
    "workflow": "Draft -> verify -> approve -> publish",
    "target": "A skeptical buyer",
    "successDefinition": "Every claim is supported and the next step is clear",
    "inputMode": "api",
    "evaluationCadence": "before-action",
    "guardrails": [
      {
        "id": "claim-proof",
        "title": "Claims are supported",
        "description": "Every quantitative claim has visible evidence or is labelled as a hypothesis.",
        "criticality": "critical",
        "enforcement": "block",
        "targetScope": "output",
        "metricType": "evidence",
        "metricConfig": {},
        "active": true,
        "source": "user"
      }
    ]
  },
  "input": {
    "text": "Publish the page claiming a 43% reduction.",
    "evidence": "Measured across 12 completed pilot incidents; analysis link: ...",
    "metrics": {},
    "binary": {},
    "checklist": {}
  }
}
```

Structured values are keyed by guardrail ID:

- `metrics[guardrailId] = number`
- `binary[guardrailId] = boolean`
- `checklist[guardrailId][itemText] = boolean`

## Result

```json
{
  "id": "evaluation UUID",
  "verdict": "pass",
  "score": 100,
  "summary": "The submitted work is supported by every active guardrail.",
  "reasoning": "...",
  "correction": "...",
  "findings": [],
  "evaluatedAt": "2026-07-06T00:00:00.000Z",
  "mode": "ai",
  "model": {
    "provider": "api.openai.com",
    "name": "gpt-5.4-mini-2026-03-17"
  },
  "requestId": "..."
}
```

A successful call transactionally refreshes the supplied guardrail set, computes the verdict, stores the server-authored audit record, and emits a sanitized `OUTCOME_VERIFIED` operational event. Raw work and free-form evidence are not copied into operational telemetry. HTTP `401`, `403`, `413`, `422`, `429`, `502`, and `504` responses include a stable error code and request ID.

## Trigger responsibility

This endpoint evaluates the payload it receives; it does not poll or observe external tools. For a `before-action`, `after-output`, or `daily` checkpoint, the integrating workflow is responsible for calling the endpoint at that boundary and supplying the current work plus evidence. Do not represent the stored checkpoint preference as active automation until that trigger exists.
