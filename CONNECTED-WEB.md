# RC Medical Transport — connected web test application

This web implementation now includes the agreed multi-page workflows. It is a sample-data test application, not a production launch or signed native app.

## Pages

Customer: Home; Book a Ride; Medical Information; Review & Confirm; Private-Pay Payment; Ride Confirmed. Additional pages: My Rides, Track My Ride, Documents, Messages & Support, My Profile.

Driver: Driver Home; Assigned Trips; Trip Details; Navigation; Update Trip Status; Complete Trip. Additional pages: Shift & Mileage, Documents, Messages.

Dispatch: Dashboard; New Trip; Today's Trips; Dispatch; Review Trip Details; Patients; Drivers; Vehicles; Eligibility / PCS / TAR; Documents; Trip Progress; Billing; Reports; Messages; Setup & Test Connection.

The routes `/`, `/passenger`, `/driver`, and `/admin` serve the application. Hash navigation selects individual screens. A test API under `/api` persists records in `connected-demo.db` on Render's ephemeral disk. Redeploys/restarts can erase records.

## Connected functionality

- Six-step customer request flow with editable assistance details, review, idempotent save and request receipt.
- Optional private-pay quote request or explicitly simulated payment choice. No card input, rate assumption, or money collection.
- Manual phone bookings, driver assignment, multiple test drivers and vehicles, editable roster and fleet records.
- Ordered driver statuses, customer/dispatch progress, pre-trip cancellation, passenger mileage at completion.
- Start/end shift odometers with invalid ending values rejected and prior shifts retained in the test record.
- In-workspace messages, sample profiles, sample eligibility/PCS/TAR review checklists.
- Sample PDF/PNG/JPEG attachments up to 128 KB, limited to 20 files per workspace. No real documents permitted.
- Reports and CSV export; test request and trip printing.
- Completed-trip billing drafts, duplicate prevention, editable review fields, starter completeness checks and a partial CMS-1500 box map. Claims remain Draft; no submission occurs.
- Optional shared workspace UUID allows test devices to use the same sample records. This is a test capability code, not role authentication.
- Address handoff to Apple Maps when explicitly clicked; no automatic GPS collection.

## Required before a real launch

Production authentication, role authorization and MFA; durable database and encrypted file storage; production audit/security controls and backups; merchant/payment integration; SMS/push provider credentials; GPS/location integration; authorized eligibility/payer/clearinghouse integration; website booking integration; iOS/Android developer accounts/signing. The original starter API is preserved for compatibility and must be secured before production.

Never enter real patient, health, insurance, identifier, or card information. View-switching and workspace codes do not supply production security.

## Validation

Python and JavaScript syntax checks; automated API workflow tests covering two drivers/fleet, idempotent booking, ordered transitions, completion, cancellation, invalid mileage rejection, session isolation, sample document encoding/type checks, messaging, sample payment/checklist records, and duplicate claim prevention. Page renderer tests cover every customer, driver, dispatch and shared page. Live browser acceptance testing follows deployment.
