# Manual MVP test guidance

## Request and constraints
Provide synthetic manual test inputs and expected results in chat. Do not upload, seed or send data to the application. No application or infrastructure changes requested.

## Sources and deliverable
Read the current native four-outcome fixtures in fastapi/scripts/scoring_stack_acceptance.py, DemoScenarios.java, frontend form/application/bank screens, demo account configuration example, and the previous backend-recheck report. Chat guidance covers common inputs, approval/counteroffer/decline/missing-data cases, document review, macro context, offer acceptance, demo signing/disbursement, refresh and document correction. Password values were not read or included. The 10% macro rate is explicitly synthetic.

## Verification and limitations
Source inspection only; no tests, model inference, browser interaction or application HTTP requests executed for this task. Prior integration results are historical evidence, not a new run. Fixture expectations depend on the pinned v2 model, selected product, matching inputs, valid macro context and completed document reviews. No data file or application records created. This report and index update implement the required local task-report workflow.

## Git state
Initial branch cookie-session, HEAD f5c2a33, tracking origin/cookie-session, clean working tree. Only this report and the shared report index changed by this task. No commit, merge or push.
