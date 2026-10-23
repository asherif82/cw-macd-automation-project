# Chartwell MACD Automation — ServiceNow, CUCM, Active Directory, and Unity Connection

Python automation for processing eligible ServiceNow **Network Account (New)** requests and provisioning Cisco collaboration resources. The supplied script is included as `end_to_end_full_macd_script_final_v1.py`.

> **Important — review before running outside a controlled test environment.** This repository documents the supplied script; it does not certify it as production-ready. The current script contains environment-specific hardcoded endpoints/settings, disables TLS certificate verification for CUCM AXL and Unity Connection requests, and has a few operational caveats documented in [`docs/REVIEW_NOTES.md`](docs/REVIEW_NOTES.md). Resolve those items and complete end-to-end testing before production use.

## What it does

1. Queries ServiceNow for eligible request items.
2. Finds the related active/open **Cisco Account Setup** task.
3. Reads employee name, username, and location variables from the request.
4. Selects an available DN matching the script's `FORMERLY HUB` logic.
5. Runs read-only preflight checks across CUCM, Active Directory, and Unity Connection.
6. Creates/updates the user's CSF/TCT device and line associations in CUCM.
7. Updates the AD `ipPhone` attribute with the selected extension.
8. Creates a Unity Connection mailbox when preflight indicates it is absent; a matching existing mailbox is left unchanged.
9. Closes the ServiceNow task on success or reassigns it to the UC team on handled failures.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the workflow diagram and [`docs/OPERATIONS.md`](docs/OPERATIONS.md) for setup and execution guidance.

## Repository contents

```text
.
├── end_to_end_full_macd_script_final_v1.py
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── SECURITY.md
└── docs/
    ├── ARCHITECTURE.md
    ├── CONFIGURATION.md
    ├── OPERATIONS.md
    ├── RECOVERY.md
    └── REVIEW_NOTES.md
```

## Requirements

- Python 3.10 or a version validated in your environment
- Network reachability to ServiceNow, CUCM AXL, Active Directory/LDAP, and Unity Connection
- AXL WSDL matching the target CUCM release
- A dedicated least-privilege service account for each integration
- A valid TLS trust chain for each HTTPS endpoint
- Permission to create/update the intended CUCM objects, modify only the AD `ipPhone` attribute, manage Unity Connection users, and update ServiceNow tasks

## Quick start

1. Create a **private** GitHub repository if the code or environment details are internal.
2. Upload the repository files. Keep `.env` out of Git; upload only `.env.example`.
3. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .\.venv\Scripts\Activate.ps1
   # Linux:
   source .venv/bin/activate

   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and populate the secrets and environment-specific values. **The current script does not yet read every environment-specific value from `.env`; see `docs/CONFIGURATION.md` and `docs/REVIEW_NOTES.md`.** Do not assume adding a variable to `.env` overrides a hardcoded constant.
5. Validate the script's hardcoded values and TLS settings against your approved test environment.
6. Test with a non-production request and dedicated test accounts. Verify the resulting CUCM, AD, CUC, and ServiceNow state independently.
7. Run:

   ```bash
   python end_to_end_full_macd_script_final_v1.py
   ```

The script currently processes requests returned by its query; it is not a dry-run tool. Do not run it against production until the review items are closed and change approval is obtained.

## Configuration files

- `.env.example`: template only; contains placeholders, never real credentials.
- `.gitignore`: excludes `.env`, Python virtual environments, bytecode, logs, and local artifacts.
- `requirements.txt`: Python dependencies imported by the script.
- `SECURITY.md`: handling and reporting guidance.

## Operational safety

- Run only with authorized, least-privilege accounts.
- Never commit passwords, tokens, private keys, real employee data, exported request records, or production logs.
- Use a dedicated test request and confirm the selected DN before authorizing writes.
- A failed run can leave partial configuration across systems. Follow [`docs/RECOVERY.md`](docs/RECOVERY.md) before retrying.
- Do not blindly rerun a failed request; reconcile the current state first.
