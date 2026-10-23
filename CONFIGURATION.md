# Configuration reference

## Important distinction

The supplied script reads some values from `.env`, but other values are constants in the Python source. `.env.example` documents the environment variables currently read and flags the settings that still need to be moved into configuration. **A variable added to `.env` has no effect unless the script reads it.**

## Environment variables read by the script

| Variable | Purpose | Required |
|---|---|---|
| `SERVICENOW_USER` | ServiceNow API username | Yes |
| `SERVICENOW_PASSWORD` | ServiceNow API password | Yes |
| `CUCM_ADDRESS` | CUCM AXL endpoint | Yes |
| `CUCM_USERNAME` | CUCM AXL username | Yes |
| `CUCM_PASSWORD` | CUCM AXL password | Yes |
| `CUCM_VERSION` | CUCM version used by AXL client | Yes |
| `AXL_WSDL` | Local path to AXL WSDL | Yes |
| `AD_SERVER` | LDAP server hostname | Yes |
| `AD_USER` | LDAP bind identity | Yes |
| `AD_PASSWORD` | LDAP bind password | Yes |
| `AD_SEARCH_BASE` | LDAP search base DN | Yes |
| `CUC_USERNAME` | Unity Connection API username | Yes |
| `CUC_PASSWORD` | Unity Connection API password | Yes |
| `UC_ASSIGNMENT_GROUP_SYS_ID` | ServiceNow UC assignment group sys_id | Confirm for your instance |
| `AXL_DEBUG` | Enables AXL SOAP payload logging when set/truthy | Optional; keep off by default |

## Values currently hardcoded in the supplied script

Review and externalize these before deployment:

- `SERVICENOW_URL` points to a test instance.
- `CUC_ADDRESS` points to a specific internal VMREST address.
- `CATALOG_ITEM_NAME`, `CATALOG_TASK_NAME`, `CATALOG_ITEM_SYS_ID`, and `sysparm_query`.
- `CUC_TEMPLATE`.
- CUCM device pool, CSS, location, MRGL, phone profile, SIP profile, partitions, line CSS, voicemail profile, and number masks.
- Other provisioning defaults and the five-second delay used in place of the documented 20-minute pause.

## AXL WSDL

`AXL_WSDL` must resolve to a local WSDL compatible with the CUCM release. Keep vendor WSDL files in a controlled local deployment path unless your organization's licensing and repository policy explicitly permit committing them. Do not place passwords in the WSDL or in source control.

## TLS

The current script sets `session.verify = False` for AXL and CUC HTTP sessions. This disables certificate verification and creates a man-in-the-middle risk. Before production use, remove this override and configure Python `requests`/Zeep to trust your organization's CA chain. Do not treat suppression of TLS warnings as a fix.

## Credential handling

- Keep `.env` local and access-controlled.
- Use distinct service accounts for ServiceNow, CUCM, AD, and CUC where possible.
- Rotate any credential that was accidentally committed or exposed.
- Do not paste `.env`, tokens, employee exports, or production logs into issues or chat.
