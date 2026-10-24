export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type Answers = Record<string, Record<string, string | number | boolean | null>>;
export type Profile = { id: string; partyId: string; rowVersion: number; answers: Answers; selectedProductVersionId?: string | null; selectedRunId?: string | null };
export type Reason = { code: string; field: string; result: string; message: string; actual: JsonValue; expected: JsonValue };
export type Product = {
  id: string; versionId: string; code: string; name: string; currency: string;
  minAmount: string; maxAmount: string; minTermMonths: number; maxTermMonths: number;
  annualRatePct: string | null; borrowerKinds: string[]; purposes: string[]; synthetic: boolean;
  policy: {
    facility_kind?: string; repayment?: string;
    pricing?: { rate_type?: string; issue_fee_rub?: number | string; maintenance_fee_rub?: number | string; unused_limit_fee_pct?: number | string };
    collateral?: { required?: boolean; kind?: string; min_own_contribution_pct?: number; max_ltv?: number | null };
    guarantor?: Record<string,string>;
    eligibility?: { min_business_age_months?: number; min_average_monthly_revenue_rub?: number; revenue_window_months?: number; extra_conditions?: string[] };
  };
};
export type Candidate = { productId: string; productVersion: string; product: Product; eligibilityStatus: 'ELIGIBLE' | 'CONDITIONAL'; pendingConditions: Reason[]; rank?: number; similarityScore?: number; isRecommended?: boolean };
export type Selection = { profileId: string; runId: string; requestId: string; current: boolean; rankingStatus: 'READY'|'EMPTY'|'NOT_CONFIGURED'|'UNAVAILABLE'|'INVALID_RESPONSE'|'NOT_REQUESTED'; results: Candidate[]; excluded: {productCode: string; reasons: Reason[]}[]; asOf: string };
export type SavedSelection = {id: string; party_id: string; company_name: string; row_version: number; created_at: string; run_id: string | null; answers: Answers};
export type Dictionaries = { purposes: Record<string,string>; sectors: Record<string,string>; usageModes: Record<string,string>; readiness: Record<string,string> };
export type Party = {id: string; name: string; access_role: string; party_kind: string};
export type Application = { id: string; applicant_party_id: string; product_version_id: string; status: string; row_version: number; created_at: string };
export type Draft = {id: string; partyId: string; productVersionId: string; status: string; answers: Answers; rowVersion: number; activeRevisionId: string | null};
export type Journey = { application: Draft; history: {to_status: string; created_at: string}[]; decision?: {kind: string; reason: string}; checks?: {evidence?: {missingFields?: string[]}} };
