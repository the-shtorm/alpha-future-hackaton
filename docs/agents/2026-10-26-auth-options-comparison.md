# Auth architecture options for the project

## Request and scope
Compare persistent browser Bearer storage and an HttpOnly-cookie server session for project logic and scalability. Advisory only; no auth implementation or configuration change.

## Sources
- Current Accounts.java/Security.java: random opaque tokens, hashed api_session records in PostgreSQL, 12-hour expiration/revocation checked on requests; existing Bearer transport. CSRF currently disabled.
- Frontend App.tsx: memory-only token; nginx exposes the API under the frontend origin.
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

## Assessment
For this same-origin browser application, recommend an opaque server-session identifier in an HttpOnly, Secure, explicitly SameSite cookie, server-side expiry/revocation, /me startup restoration and appropriate CSRF protection. Reuse api_session rather than adding JWT/refresh machinery solely to fix reload. HttpOnly prevents script extraction of the cookie; XSS may still perform authenticated actions, so it does not replace XSS prevention. CSRF protections are required for the cookie-auth mutations; SameSite is defense in depth.

Bearer saved in sessionStorage is a small frontend persistence change but exposes the credential to origin JavaScript and is tab-scoped. OWASP discourages keeping authentication credentials in either Web Storage API. The previous recommendation was a quick demo-repair option, not the preferred long-term architecture.

Browser storage/transport and backend scaling are separate axes. Both proposed designs can reuse the same shared PostgreSQL session table across Java replicas without sticky sessions. Cookies alone neither require local server memory nor add a session lookup compared with the current opaque Bearer implementation. Redis is a possible later store/cache only if measurements warrant it; do not weaken revocation consistency via an unspecified cache.

JWT is a token format; Bearer and cookies describe different transport/use aspects. A locally verified JWT can avoid an opaque-session lookup only with a deliberate authorization/revocation design. Its operational costs include key management, expiry/refresh and role/revocation propagation; it is not automatically the more scalable choice for this application's current architecture. Keep Bearer support available for future mobile/integration callers as a separate client-facing auth contract.

Renewal is a distinct policy: enforce idle and absolute lifetimes; never renew indefinitely merely because a tab is open. A dedicated rotating refresh flow is an option when short-lived API access tokens/multiple clients become an actual requirement, not a prerequisite for page reload restoration.

## Verification and deliverable
Read current relevant source references and nginx config; browsed the two authoritative OWASP references. No application tests, load measurements or auth changes performed. Decision is an architectural recommendation tailored to the current source, not a measured performance claim. New report/shared-index entry only; no commit or push.
