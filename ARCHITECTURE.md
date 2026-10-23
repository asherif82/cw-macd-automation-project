# Architecture and execution flow

## High-level path

```mermaid
flowchart TD
    A([Start]) --> B[Load local .env]
    B --> C[Query eligible ServiceNow RITMs]
    C --> D{Any RITMs?}
    D -- No --> Z([Exit])
    D -- Yes --> E[Find active/open Cisco Account Setup task]
    E --> F{Task found?}
    F -- No --> C
    F -- Yes --> G[Read employee variables]
    G --> H[Find available FORMERLY HUB DN]
    H --> I[Read-only preflight: CUCM, AD, CUC]
    I --> J{Conflicts?}
    J -- Yes --> K[Record failure details and stop provisioning]
    K --> R[Add work notes and reassign task to UC]
    J -- No --> L[Create CSF/TCT and CUCM line/device associations]
    L --> M{CUCM steps successful?}
    M -- No --> R
    M -- Yes --> N[Update AD ipPhone]
    N --> O{AD update successful?}
    O -- No --> R
    O -- Yes --> P[Create CUC mailbox if absent]
    P --> Q{CUC successful?}
    Q -- No --> R
    Q -- Yes --> S[Write success notes and close task]
    R --> T[Continue/finish loop]
    S --> T
    T --> C
```

## Systems and responsibilities

| Component | Role | Main operations |
|---|---|---|
| ServiceNow | Work queue and request data | Query request items/tasks, read variables, update notes/state/assignment |
| CUCM AXL | Call-control provisioning | Select a reusable DN, create CSF/TCT devices, update lines, associate devices/users |
| Active Directory | Directory metadata | Read user `ipPhone`; update that attribute to the selected extension |
| Unity Connection CUPI/VMREST | Voicemail provisioning | Check mailbox state and create mailbox using the configured template |
| Local environment | Runtime configuration | Load credentials from `.env` and locate the AXL WSDL |

## Preflight intent

The preflight checks are intended to detect conflicting state before writes. It checks the selected extension and related CUCM objects, the AD `ipPhone` value, and whether a CUC mailbox exists with a matching DTMF access ID. A preflight pass is not a transaction guarantee: state can change between checks and writes, and downstream operations can still fail.

## Cross-system consistency

CUCM, AD, CUC, and ServiceNow do not share a transaction. If an operation succeeds in one system and a later step fails, the script may leave a partial result. Use the reconciliation procedure in [`RECOVERY.md`](RECOVERY.md); do not assume that retrying the whole request is idempotent.
