# Operations runbook

## 1. Before first run

1. Confirm approval to run against the target environment.
2. Verify the ServiceNow URL, catalog item/task identifiers, assignment group, and query logic.
3. Verify the CUCM AXL endpoint and compatible WSDL.
4. Verify the AD bind account can search the intended OU/base and modify only `ipPhone`.
5. Verify the CUC endpoint, API permissions, and mailbox template alias.
6. Resolve the TLS certificate-verification issue described in `CONFIGURATION.md`.
7. Confirm the selected `FORMERLY HUB` DN is eligible for reuse and is not in active use.
8. Run a code review and syntax check.

## 2. Create the Python environment

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# Linux
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, then replace all placeholders with approved values. Never commit `.env`.

## 3. Validate the environment

```bash
python --version
python -m pip check
python -m py_compile end_to_end_full_macd_script_final_v1.py
```

These checks validate the Python environment and syntax only; they do not test credentials or API permissions.

## 4. Controlled test procedure

1. Use a dedicated test request and test user.
2. Confirm the RITM is eligible and the related Cisco Account Setup task is active/open.
3. Verify the employee variables resolve to the intended account.
4. Observe the preflight output and confirm no conflicting DN/device/AD/voicemail state.
5. After each run, independently verify CUCM CSF/TCT devices and line associations, AD `ipPhone`, CUC mailbox/DTMF access ID, and ServiceNow task status/notes.
6. Test each failure path in a non-production environment: preflight conflict, CUCM write failure, AD failure, CUC failure, and ServiceNow update failure.
7. Confirm a failure is routed to the UC assignment group with actionable work notes.
8. Record the test case, result, and approver in the organization's change record.

## 5. Normal execution

Run from the directory containing the script and `.env`:

```bash
python end_to_end_full_macd_script_final_v1.py
```

The script performs real writes; it does not provide a built-in dry-run mode. The active-RITM loop should be reviewed carefully before execution because the current source has a commented-out `break` and may continue through multiple eligible requests.

## 6. Success criteria

- CUCM has the expected CSF/TCT devices and associations.
- The selected DN and line settings match the approved design.
- AD `ipPhone` equals the selected extension.
- CUC mailbox is created or an existing matching mailbox is intentionally retained.
- ServiceNow task has success work notes and is closed only after all required steps succeed.

## 7. Failure criteria

Treat the run as incomplete if any downstream system fails, even if CUCM device creation succeeded. Capture the RITM/task number in the internal change record, redact sensitive details from logs, and use `RECOVERY.md` before retrying.
