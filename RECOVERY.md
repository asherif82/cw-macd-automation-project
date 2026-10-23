# Recovery and reconciliation after partial provisioning

## Principle

There is no distributed transaction across ServiceNow, CUCM, Active Directory, and Unity Connection. A failed run can leave some writes committed. **Do not blindly rerun the script** until the actual state has been inspected.

## 1. Stop and capture

- Stop additional executions for the affected request/user.
- Record the RITM and Cisco Account Setup task identifiers in the approved internal ticket.
- Capture the console output and timestamp, removing passwords, tokens, and unnecessary personal data.
- Identify the last confirmed successful step and the first failed step.

## 2. Read-only reconciliation checklist

| System | Inspect | Expected state to compare |
|---|---|---|
| ServiceNow | RITM and task state, assignment, work notes | Task remains open/reassigned if provisioning is incomplete |
| CUCM | Selected DN, CSF/TCT devices, owner user ID, line/device associations | Objects exist only as intended; DN and line associations are correct |
| Active Directory | User `ipPhone` attribute | Empty/previous value or selected extension, as expected for the completed steps |
| Unity Connection | Mailbox alias and `DtmfAccessId` | Absent or present with the intended extension |
| Logs | Error message and operation order | Establish which writes completed; redact secrets |

Use approved admin interfaces or read-only API queries. Do not delete or overwrite objects solely because their names look similar.

## 3. Decision guide

- **Preflight conflict:** Do not proceed until the existing DN, devices, AD attribute, and mailbox have been reviewed and the conflict resolved by an authorized administrator.
- **CUCM device/association failure:** Inspect all relevant CUCM objects before retrying. Remove or repair partial objects only under an approved change plan.
- **AD update failure after CUCM success:** Keep the request open/reassigned. Confirm the intended user and extension, then repair `ipPhone` through the approved process or rerun only after idempotency has been established.
- **CUC mailbox failure after CUCM/AD success:** Check whether a mailbox was created despite the client-side failure. Verify alias and DTMF access ID before attempting creation again.
- **ServiceNow close/update failure after provisioning success:** Do not reprovision. Verify all systems first, then update task notes/state manually through the approved process.
- **Unknown outcome / timeout:** Treat the result as ambiguous. Query the target system before retrying because the server may have committed the request even if the client timed out.

## 4. Completion

After repair, independently verify CUCM, AD, CUC, and ServiceNow. Record the reconciled state, changes made, approvals, and final outcome in the internal ticket. Do not store raw employee exports or credentials in this repository.
