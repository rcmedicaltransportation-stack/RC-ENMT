# RC Medical Transport — NEMT Management System

A working starter-to-production foundation for:
- Manual ride entry
- Website ride requests with accept/decline
- Client, driver, vehicle and payer records
- Ambulatory / wheelchair / gurney trips
- Dispatch and trip status
- Ready-to-Bill queue after completion
- Private-pay invoices and receipts
- Insurance claim preparation/tracking
- SMS notification hooks, including 5-minutes-away
- Website booking API

## Run

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Open http://127.0.0.1:8000/docs for the API.

## Important production work
Before using real patient data, add authentication/roles, encryption, audit logging,
backups, secure hosting, BAAs with vendors where applicable, and a compliant SMS/payment setup.
Do not put sensitive medical details in ordinary SMS messages.

Insurance claims are staged in the billing queue. Connect the `submit_claim_to_clearinghouse`
adapter to the approved clearinghouse/payer interface for each payer.
