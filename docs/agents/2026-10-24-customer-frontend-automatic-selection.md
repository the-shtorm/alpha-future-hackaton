# Customer frontend and automatic selection — 2026-10-24

Status: paused at the user’s request on 2026-10-24. Branch: backend-tasks_v2. Separate task report.

## Request

Redesign the interface for end customers, add a usable catalog, remove hackathon/engineering
presentation and manual JSON handoffs. Read dataset_fields_review.md. The user confirms
there is no Recsys HTTP endpoint yet. Model implementation remains another team's work.

## Decisions

Catalog, product details, form, saved selections and applications should be normal user flows.
Backend performs any configured Recsys exchange itself. With no endpoint, expose checked
products and an honest unavailable state; do not fabricate a ranking. Keep all candidates
and Java applicability conditions. Do not show cosine numbers as approval probabilities.
SBA reference describes proposed risk data, not a replacement customer questionnaire:
no 42-column form, outcome leakage, implicit RUB->USD, OKVED->NAICS, LLC/IP->US mappings,
or collateral-readiness->verified-collateral substitution. No model or dataset pipeline.

## Work / verification

Pending implementation and verification. Prior task reports stay unchanged.

## Scope change

The user paused the frontend redesign and supplied corrected Preliminary Form 2.0 and
Data Policy 3.0. Backend field alignment continues as a separate task/report. Existing
frontend edits and automatic adapter are unfinished and retained; no frontend build or
customer-flow verification is claimed. Dataset review is not the governing form contract.
