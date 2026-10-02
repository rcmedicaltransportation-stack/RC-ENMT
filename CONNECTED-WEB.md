# Connected web test version

The Render homepage now serves customer, driver, and admin/dispatch browser views. The saved React Native starters were adapted into a dependency-free mobile-friendly web interface; this is not an App Store build.

Routes: `/`, `/passenger`, `/driver`, `/admin`. All browser views call `/api` on the same host. Records are scoped to a randomly generated browser test session in localStorage; a separate browser/device has a separate session. The connector stores test records in SQLite `connected-demo.db`, on Render's ephemeral filesystem. Restart/redeploy can reset records.

Verified workflow: customer request → dispatch assignment → driver pickup/destination status → customer status → completion with passenger mileage → draft billing record. Phone bookings and shift start/end odometer totals share the same test backend.

Billing drafts are ride summaries for review, not validated CMS-1500 forms or submitted claims. No procedure codes or rates are guessed. Login/roles, persistent secure database, secure document and odometer-photo storage, GPS/background tracking, notifications, payments, payer integration and native app releases still require implementation and external setup. Use only sample data.

The original API remains present for compatibility and is not activated as a production integration by this change.

Validation: Python syntax, JavaScript syntax, FastAPI TestClient tests for all four HTML routes, booking/assignment/status/completion, mileage, duplicate draft prevention, invalid odometer rejection, and separation between test sessions.

Package comparison: Connected-App2027 contains the shared API wiring; Final-Demo2026 9 contains a richer but local-state-only billing view. The web adaptation combines the shared workflow with editable sample claim fields, persisted draft review, missing-field checks and a partial CMS-1500 field preview. It does not transmit claims or validate payer-specific rules.
