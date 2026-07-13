# DriftGuard LLM Simulation Report

All records below are **SIMULATED hypotheses**, not observed user evidence.

| ID     | Persona                                    | Scenario                                                         | Simulated finding                                                                                                     | New/exposed gaps                   | Severity |
| ------ | ------------------------------------------ | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ---------------------------------- | -------: |
| SIM-01 | First-time operator                        | Uses local demo without signing in                               | Flow is clear, but sample state and universal snapshot claims can imply persistence/AI that local mode lacks.         | DG-G008, DG-G023                   |        4 |
| SIM-02 | Expert operator                            | Edits policy on laptop, evaluates from stale integration payload | Evaluation payload can refresh/overwrite policy without version check.                                                | DG-G002, DG-G016                   |        5 |
| SIM-03 | Skeptical buyer                            | Asks for proof that DriftGuard prevented errors                  | Only evaluation activity exists; OUTCOME_VERIFIED is not a real outcome.                                              | DG-G004, DG-G009, DG-G010, DG-G022 |        5 |
| SIM-04 | Administrator                              | Configures pilot with sensitive workflow content                 | Secrets/RLS are designed, but governance and ownership controls are absent.                                           | DG-G005, DG-G006, DG-G017, DG-G018 |        5 |
| SIM-05 | Failure-state operator                     | AI provider times out during a high-impact check                 | Local preview substitutes after a transient flash; mode is small footer text.                                         | DG-G014, DG-G019                   |        4 |
| SIM-06 | Adversarial authenticated user/integration | Sends altered workspace with evaluation request                  | Function persists supplied workspace before evaluating.                                                               | DG-G002, DG-G003                   |        5 |
| SIM-07 | Two users on one shared browser            | User A signs out; User B opens app                               | Local workspace remains and may show User A's constraints.                                                            | DG-G007                            |        5 |
| SIM-08 | Time-pressured operator                    | Needs a verdict during provider degradation                      | Core UI is fast, but degraded authority is not prominent enough.                                                      | DG-G014                            |        4 |
| SIM-09 | Low-context user                           | Supplies vague purpose and generic success statement             | AI/local inference can create plausible but generic guardrails; review is available, but no confidence/quality gate.  | DG-G009, DG-G023                   |        3 |
| SIM-10 | High-context user                          | Pastes long policy and evidence                                  | Character limits exist, but no token-budget estimate, retrieval, provenance references, or evidence attachment model. | DG-G005, DG-G009                   |        3 |
| SIM-11 | Longitudinal repeat user                   | Returns after multiple workflows and policy changes              | Only latest set loads; current rules have no meaningful version lineage; evaluations are hidden.                      | DG-G013, DG-G016, DG-G021          |        4 |
| SIM-12 | Integrator handoff                         | Another developer operationalizes before-action checks           | Docs describe user-token calls but not durable unattended integration or support ownership.                           | DG-G012, DG-G018                   |        4 |

## Evidence rule

These simulations may prioritize real tests, but they cannot close any evidence gap. Every P0–P2 conclusion still requires the acceptance evidence in `ACCEPTANCE_TESTS.yaml`.
