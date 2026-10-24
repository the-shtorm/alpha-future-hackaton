# Demo account check — 2026-10-24

Completed. User asked for the demo user's password.

Read the demo-account initialization code and checked only the relevant local config.
The running Compose database has no demo-owner row; DEMO_PASSWORD is not configured
in .env. Startup does not create the optional account without that value. Explained
how to configure it and distinguished the earlier isolated preview's credentials.
No credentials/hashes are included here. No account, password, configuration or
service was changed. Read-only database query returned no matching login.
Branch backend-tasks_v2; no commit or push. Prior uncommitted changes preserved.
