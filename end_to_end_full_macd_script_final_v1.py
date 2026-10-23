import os
import json
import sys
from time import time
from time import sleep
import requests
from dotenv import load_dotenv
import urllib3
import logging
from lxml import etree
import pprint
from pprint import pprint
from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client, Settings, Plugin
from zeep.transports import Transport
from zeep.exceptions import Fault
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.core.exceptions import LDAPException
from pathlib import Path
from ldap3 import Server, Connection, ALL

ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_FILE, override=True)

# load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# ============================================================
# ServiceNow Configuration
# ============================================================

SERVICENOW_URL = "https://chartwelltest.service-now.com"
SERVICENOW_USER = os.getenv("SERVICENOW_USER")
SERVICENOW_PASSWORD = os.getenv("SERVICENOW_PASSWORD")

# ============================================================
# ServiceNow Catalog Configuration
# ============================================================

CATALOG_ITEM_NAME = "Network Account (New)"
CATALOG_TASK_NAME = "Cisco Account Setup"
CATALOG_ITEM_SYS_ID = "7d0a82a1dbb8c05033a858b8dc9619c3"
sysparm_query = f"cat_s={CATALOG_ITEM_NAME}"

# FOR TESTING
# RITM_SYS_ID = "e07502f4939b4710c7aff42e1dba1026"
# RITM_NUMBER = "RITM2432735"

# Internal variable names
SNOW_FIRST_NAME_VARIABLE = "employee_first_name"
SNOW_LAST_NAME_VARIABLE = "employee_last_name"
SNOW_USERNAME_VARIABLE = "employee_username"
SNOW_LOCATION_VARIABLE = "employee_location"

# ServiceNow assignment group
# IMPORTANT:
# Replace this with the actual sys_id of your UC team assignment group.
UC_ASSIGNMENT_GROUP_SYS_ID = os.getenv("UC_ASSIGNMENT_GROUP_SYS_ID")

# ---------------------------------------------------------------------------
# CUCM Connection settings
# ---------------------------------------------------------------------------
CUCM_ADDRESS = os.getenv("CUCM_ADDRESS")
CUCM_USERNAME = os.getenv("CUCM_USERNAME")
CUCM_PASSWORD = os.getenv("CUCM_PASSWORD")
CUCM_VERSION = os.getenv("CUCM_VERSION")
WSDL_FILE = os.getenv("AXL_WSDL")

# ---------------------------------------------------------------------------
# CUC Connection settings
# ---------------------------------------------------------------------------
CUC_ADDRESS = "https://172.25.116.112/vmrest"
CUC_USERNAME = os.getenv("CUC_USERNAME")
CUC_PASSWORD = os.getenv("CUC_PASSWORD")
CUC_TEMPLATE = "Hub_VM_User_Template"

# ---------------------------------------------------------------------------
# Device / line parameters
# ---------------------------------------------------------------------------

DISPLAY_NAME = f'{SNOW_FIRST_NAME_VARIABLE} {SNOW_LAST_NAME_VARIABLE}'
DISPLAY_ASCII = f'{SNOW_FIRST_NAME_VARIABLE} {SNOW_LAST_NAME_VARIABLE}'
DESCRIPTION = 'HUB - ' + SNOW_FIRST_NAME_VARIABLE + ' ' + SNOW_LAST_NAME_VARIABLE
ALERTING_NAME = f'{SNOW_FIRST_NAME_VARIABLE} {SNOW_LAST_NAME_VARIABLE}'
ASCII_ALERTING_NAME = f'{SNOW_FIRST_NAME_VARIABLE} {SNOW_LAST_NAME_VARIABLE}'
DEVICE_POOL = 'Corp-Hub-DP'
DEVICE_CSS = 'Hub-Device-CSS'
FORWARD_CSS = 'Hub-LD-Forwarding-CSS'
LOCATION = 'Hub-Loc'
MRGL = 'Hub-MRGL'
PHONE_CONFIG_NAME = 'Standard Common Phone Profile'
SIP_PROFILE = 'Standard SIP Profile for Mobile Device'
CSF_PRODUCT = 'Cisco Unified Client Services Framework'
TCT_PRODUCT = 'Cisco Dual Mode for iPhone'
DEVICE_PROTOCOL = 'SIP'
HUB_PARTITION = 'Hub-Internal-PT'
LINE_CSS = 'Centralized-LD-CSS'
VOICEMAIL_PROFILE = 'Chartwell_VM_Profile'
ENTERPRISE_NUMBER_MASK = '905501XXXX'
ENTERPRISE_ALTERNATE_NUMBER = '905501XXXX'
E164_ALTERNATE_NUMBER = '+1905501XXXX'
ADVERTISE_GLOBALLY = True

# ---------------------------------------------------------
# AD CONFIGURATION
# ---------------------------------------------------------
ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_FILE, override=True)

AD_SERVER = os.getenv("AD_SERVER", "").strip()
AD_USER = os.getenv("AD_USER", "").strip()
AD_PASSWORD = os.getenv("AD_PASSWORD", "")
AD_SEARCH_BASE = os.getenv("AD_SEARCH_BASE", "").strip()

if not all([AD_SERVER, AD_USER, AD_PASSWORD, AD_SEARCH_BASE]):
    raise ValueError(
        "Missing AD configuration. Check AD_SERVER, AD_USER, "
        "AD_PASSWORD, and AD_SEARCH_BASE in .env"
    )

# ---------------------------------------------------------------------------------------------#
# ***************************          CALLMANAGER FUNCTIONS          *************************#
# ---------------------------------------------------------------------------------------------#

# ---------------------------------------------------------------------------
# 1.CUCM Logging plugin
# ---------------------------------------------------------------------------


class LoggingPlugin(Plugin):
    """Optional AXL request/response logger (enable with AXL_DEBUG=1)."""

    def egress(self, envelope, http_headers, operation, binding_options):
        if os.getenv('AXL_DEBUG'):
            from lxml import etree
            print(etree.tostring(envelope, pretty_print=True).decode())
        return envelope, http_headers

    def ingress(self, envelope, http_headers, operation):
        if os.getenv('AXL_DEBUG'):
            from lxml import etree
            print(etree.tostring(envelope, pretty_print=True).decode())
        return envelope, http_headers

# ---------------------------------------------------------------------------
# 2.Get AXL client instance
# ---------------------------------------------------------------------------


def get_axl_client():
    session = Session()
    session.verify = False
    session.auth = HTTPBasicAuth(CUCM_USERNAME, CUCM_PASSWORD)

    transport = Transport(session=session, timeout=30)
    settings = Settings(strict=False, xml_huge_tree=True)

    client = Client(wsdl=WSDL_FILE, settings=settings,
                    transport=transport, plugins=[LoggingPlugin()])

    service = client.create_service(
        '{http://www.cisco.com/AXLAPIService/}AXLAPIBinding',
        f'https://{CUCM_ADDRESS}:8443/axl/')
    return service

# ---------------------------------------------------------------------------
# 3.function to find the lowest available FORMERLY HUB extension
# ---------------------------------------------------------------------------


def find_formerly_extension(service):
    # Find the lowest available FORMERLY HUB extension
    # Finds Lines in HUB_PARTITION.
    # Checks description == "FORMERLY HUB".

    # Steps:
    # 1. List all lines in the HUB_PARTITION.
    # 2. Filter lines with description "FORMERLY HUB".
    # 3. Check the Route Plan for each candidate line.
    # 4. Keep only lines with empty routeDetail.
    # 5. Sort the remaining lines numerically.
    # 6. Select the lowest one as FORMERLY_EXT.

    # Conditions:
    #   1. Line description must be "FORMERLY HUB"
    #   2. Route Plan Route Detail must be empty
    #
    # Returns:
    #   FORMERLY_EXT = lowest numeric matching extension
    #   None         = no matching extension found

    try:
        # ---------------------------------------------------------------
        # Get all lines in the Hub partition
        # ---------------------------------------------------------------
        response = service.listLine(
            searchCriteria={
                "routePartitionName": HUB_PARTITION
            },
            returnedTags={
                "pattern": True,
                "description": True,
                "routePartitionName": True
            }
        )

        lines = getattr(response["return"], "line", None)

        if not lines:
            print("\nNo lines found in HUB partition.")
            return None

        # Zeep can return one object or a list
        if not isinstance(lines, list):
            lines = [lines]

        candidates = []

        # ---------------------------------------------------------------
        # Check each Line
        # ---------------------------------------------------------------
        for line in lines:

            extension = getattr(line, "pattern", None)
            description = getattr(line, "description", None)

            if not extension:
                continue

            print(
                f"Checking Line: {extension} | "
                f"Description: {description}"
            )

            # -----------------------------------------------------------
            # Condition #1
            # -----------------------------------------------------------
            if description != "FORMERLY HUB":
                continue

            print(f"  -> FORMERLY HUB found: {extension}")

            # -----------------------------------------------------------
            # Check Route Plan for this extension
            # -----------------------------------------------------------
            route_response = service.listRoutePlan(
                searchCriteria={
                    "dnOrPattern": extension
                },
                returnedTags={
                    "dnOrPattern": True,
                    "partition": True,
                    "type": True,
                    "routeDetail": True
                }
            )

            route_plans = getattr(
                route_response["return"],
                "routePlan",
                None
            )

            # No Route Plan entry
            if not route_plans:
                print(f"  -> No Route Plan entry found for {extension}")
                continue

            # Zeep can return one object or a list
            if not isinstance(route_plans, list):
                route_plans = [route_plans]

            route_detail_found = False

            for route in route_plans:

                route_detail = getattr(
                    route,
                    "routeDetail",
                    None
                )

                if route_detail:
                    print(
                        f"  -> Route Detail found for "
                        f"{extension}: {route_detail}"
                    )
                    route_detail_found = True
                    break

            # -----------------------------------------------------------
            # Condition #2
            # Route Detail must be empty
            # -----------------------------------------------------------
            if route_detail_found:
                continue

            print(
                f"  -> MATCH: {extension} "
                f"(FORMERLY HUB + empty Route Detail)"
            )

            candidates.append(extension)

        # ---------------------------------------------------------------
        # No candidates found
        # ---------------------------------------------------------------
        if not candidates:
            print(
                "\nNo FORMERLY HUB extensions with "
                "empty Route Detail were found."
            )
            return None

        # ---------------------------------------------------------------
        # Sort numerically
        # ---------------------------------------------------------------
        candidates.sort(key=int)

        # Lowest numeric extension
        FORMERLY_EXT = candidates[0]

        print("\n===== FORMERLY HUB CANDIDATES =====")
        print(f"Candidates: {candidates}")
        print(f"Selected FORMERLY_EXT: {FORMERLY_EXT}")
        print("===================================\n")
        SPARE_EXTENSION = FORMERLY_EXT
        return FORMERLY_EXT

    except Fault as e:
        print("\nERROR finding FORMERLY HUB extension:")
        print(e)
        return None

# ---------------------------------------------------------------------------
# 4.Create a CSF and TCT phone and associate the spare DN with it
# ---------------------------------------------------------------------------


def create_csf_phone(service, formerly_ext):
    """
    Create a Cisco Unified Client Services Framework (CSF) device
    and associate the spare DN with the device.
    """
    # Print a message indicating the creation of the CSF device with removing the - from the device name if necessary
    print(f"\nCreating CSF device: {CSF_DEVICE_NAME}")

    phone = {
        'name': CSF_DEVICE_NAME,
        'description': DESCRIPTION,

        'product': CSF_PRODUCT,
        'class': 'Phone',
        'protocol': DEVICE_PROTOCOL,

        'devicePoolName': {
            '_value_1': DEVICE_POOL
        },

        'callingSearchSpaceName': {
            '_value_1': DEVICE_CSS
        },

        'commonPhoneConfigName': {
            '_value_1': PHONE_CONFIG_NAME
        },

        'locationName': {
            '_value_1': LOCATION
        },

        'mediaResourceListName': {
            '_value_1': MRGL
        },

        'sipProfileName': {
            '_value_1': SIP_PROFILE
        },

        'ownerUserName': {
            '_value_1': OWNER_USER_ID
        },

        'lines': {
            'line': [
                {
                    'index': 1,

                    'label': ALERTING_NAME,

                    'display': DISPLAY_NAME,

                    'displayAscii': DISPLAY_ASCII,

                    'dirn': {
                        'pattern': formerly_ext,
                        'routePartitionName': {
                            '_value_1': HUB_PARTITION
                        }
                    },

                    'e164Mask': '+1905501' + formerly_ext
                }
            ]
        }
    }

    try:
        response = service.addPhone(
            phone=phone,
            sequence=1
        )

        print(f"CSF device created successfully: {CSF_DEVICE_NAME}")
        print(f"DN {formerly_ext} associated with {CSF_DEVICE_NAME}")

        return True

    except Fault as e:
        print("\nAXL ERROR creating CSF device:")
        print(e)
        return False

    except Exception as e:
        print("\nERROR preparing CSF device creation:")
        print(e)
        return False


def create_tct_phone(service, formerly_ext):
    """
    Create a Cisco Dual Mode for iPhone (TCT) device
    and associate the spare DN with the device.
    """

    print(f"\nCreating TCT device: {TCT_DEVICE_NAME}")

    phone = {
        'name': TCT_DEVICE_NAME,
        'description': DESCRIPTION,

        'product': TCT_PRODUCT,
        'class': 'Phone',
        'protocol': DEVICE_PROTOCOL,

        'devicePoolName': {
            '_value_1': DEVICE_POOL
        },

        'callingSearchSpaceName': {
            '_value_1': DEVICE_CSS
        },

        'commonPhoneConfigName': {
            '_value_1': PHONE_CONFIG_NAME
        },

        'locationName': {
            '_value_1': LOCATION
        },

        'mediaResourceListName': {
            '_value_1': MRGL
        },

        'sipProfileName': {
            '_value_1': SIP_PROFILE
        },

        'ownerUserName': {
            '_value_1': OWNER_USER_ID
        },

        'lines': {
            'line': [
                {
                    'index': 1,

                    'label': ALERTING_NAME,

                    'display': DISPLAY_NAME,

                    'displayAscii': DISPLAY_ASCII,

                    'dirn': {
                        'pattern': formerly_ext,
                        'routePartitionName': {
                            '_value_1': HUB_PARTITION
                        }
                    },

                    'e164Mask': '+1905501' + formerly_ext
                }
            ]
        }
    }

    try:
        response = service.addPhone(
            phone=phone,
            sequence=1
        )

        print(f"TCT device created successfully: {TCT_DEVICE_NAME}")
        print(f"DN {formerly_ext} associated with {TCT_DEVICE_NAME}")

        return True

    except Fault as e:
        print("\nAXL ERROR creating TCT device:")
        print(e)
        return False

    except Exception as e:
        print("\nERROR preparing TCT device creation:")
        print(e)
        return False

# ---------------------------------------------------------------------------
# 5.Update the line (DN) configuration for the spare extension in CUCM
# ---------------------------------------------------------------------------


def update_line(service, formerly_ext):
    """
    Update the CUCM DN-level configuration.
    This includes description, alerting name,
    call forwarding and alternate numbers.
    """

    line = {
        'pattern': formerly_ext,
        'routePartitionName': HUB_PARTITION,

        'description': DESCRIPTION,

        'alertingName': ALERTING_NAME,
        'asciiAlertingName': ASCII_ALERTING_NAME,

        'callForwardBusyInt': {
            'forwardToVoiceMail': True
        },

        'callForwardBusy': {
            'forwardToVoiceMail': True
        },

        'callForwardNoAnswerInt': {
            'forwardToVoiceMail': True
        },

        'callForwardNoAnswer': {
            'forwardToVoiceMail': True
        },

        'callForwardNoCoverageInt': {
            'forwardToVoiceMail': True
        },

        'callForwardNoCoverage': {
            'forwardToVoiceMail': True
        },

        'callForwardOnFailure': {
            'forwardToVoiceMail': True
        },

        'callForwardNotRegisteredInt': {
            'forwardToVoiceMail': True
        },

        'callForwardNotRegistered': {
            'forwardToVoiceMail': True
        },

        # Explicitly make sure Call Forward All is NOT enabled
        'callForwardAll': {
            'forwardToVoiceMail': False,
            'callingSearchSpaceName': FORWARD_CSS
        },

        # Enterprise Alternate Number
        'enterpriseAltNum': {
            'numMask': ENTERPRISE_ALTERNATE_NUMBER,
            'addLocalRoutePartition': True,
            'routePartition': 'Chartwell-Internal-ALL',
            'advertiseGloballyIls': ADVERTISE_GLOBALLY
        },

        # +E.164 Alternate Number
        'e164AltNum': {
            'numMask': E164_ALTERNATE_NUMBER,
            'addLocalRoutePartition': True,
            'routePartition': 'Chartwell-Internal-ALL',
            'advertiseGloballyIls': ADVERTISE_GLOBALLY
        },

        'useEnterpriseAltNum': True,
        'useE164AltNum': True,
    }

    print(f"\nUpdating DN: {formerly_ext}")

    try:
        response = service.updateLine(**line)

        print(f"DN {formerly_ext} updated successfully.")

        return True

    except Fault as e:
        print("\nERROR updating line:")
        print(e)
        return False

# ---------------------------------------------------------------------------
# 6. Associates a device to a user in CUCM, ensuring the device is added to the user's
#   existing associated devices without removing any current devices.
# ---------------------------------------------------------------------------


def associate_csf_device_to_user(service, formerly_ext):
    """
    Add the new CSF device to the user's existing associated devices
    without removing any existing devices.

    Also sets the user's primary extension.
    """

    print(f"\nRetrieving existing devices for user {OWNER_USER_ID}")

    try:
        # ---------------------------------------------------------------
        # 1. Get the user's current configuration
        # ---------------------------------------------------------------
        response = service.getUser(
            userid=OWNER_USER_ID
        )

        user = response['return']['user']

        # ---------------------------------------------------------------
        # 2. Get existing associated devices
        # ---------------------------------------------------------------
        existing_devices = []

        if user.associatedDevices:
            existing_devices = list(user.associatedDevices.device)
        print(existing_devices)
        print("\nExisting associated devices:")

        for device in existing_devices:
            print(f"  - {device}")

        # ---------------------------------------------------------------
        # 3. Add the new CSF
        # ---------------------------------------------------------------
        if CSF_DEVICE_NAME not in existing_devices:

            existing_devices.append(CSF_DEVICE_NAME)

            print(f"\nAdding new device: {CSF_DEVICE_NAME}")

        else:

            print(
                f"\nDevice {CSF_DEVICE_NAME} is already "
                f"associated with user {OWNER_USER_ID}"
            )

        # ---------------------------------------------------------------
        # 4. Build the complete device list
        # ---------------------------------------------------------------
        devices = {
            'device': existing_devices
        }

        print("\nFinal device list that will be sent to CUCM:")

        for device in existing_devices:
            print(f"  - {device}")

        # ---------------------------------------------------------------
        # 5. Set Primary Extension
        # ---------------------------------------------------------------
        primary_extension = {
            'pattern': formerly_ext,
            'routePartitionName': HUB_PARTITION
        }

        # ---------------------------------------------------------------
        # 6. Update the user
        # ---------------------------------------------------------------
        service.updateUser(
            userid=OWNER_USER_ID,
            associatedDevices=devices,
            primaryExtension=primary_extension,
            homeCluster=True,
            imAndPresenceEnable=True
        )

        print(
            f"\nDevice {CSF_DEVICE_NAME} associated to user "
            f"{OWNER_USER_ID} successfully."
        )

        print(
            f"Primary extension {formerly_ext} "
            f"assigned to user {OWNER_USER_ID}."
        )

        return True

    except Fault as e:
        print("\nAXL ERROR associating device / updating user:")
        print(e)
        return False

    except Exception as e:
        print("\nERROR preparing user update:")
        print(e)
        return False


def associate_tct_device_to_user(service, formerly_ext):
    """
    Add the new TCT device to the user's existing associated devices
    without removing any existing devices.

    Also sets the user's primary extension.
    """

    print(f"\nRetrieving existing devices for user {OWNER_USER_ID}")

    try:
        # ---------------------------------------------------------------
        # 1. Get the user's current configuration
        # ---------------------------------------------------------------
        response = service.getUser(
            userid=OWNER_USER_ID
        )

        user = response['return']['user']

        # ---------------------------------------------------------------
        # 2. Get existing associated devices
        # ---------------------------------------------------------------
        existing_devices = []

        if user.associatedDevices:
            existing_devices = list(user.associatedDevices.device)
        print(existing_devices)
        print("\nExisting associated devices:")

        for device in existing_devices:
            print(f"  - {device}")

        # ---------------------------------------------------------------
        # 3. Add the new TCT
        # ---------------------------------------------------------------
        if TCT_DEVICE_NAME not in existing_devices:

            existing_devices.append(TCT_DEVICE_NAME)

            print(f"\nAdding new device: {TCT_DEVICE_NAME}")

        else:

            print(
                f"\nDevice {TCT_DEVICE_NAME} is already "
                f"associated with user {OWNER_USER_ID}"
            )

        # ---------------------------------------------------------------
        # 4. Build the complete device list
        # ---------------------------------------------------------------
        devices = {
            'device': existing_devices
        }

        print("\nFinal device list that will be sent to CUCM:")

        for device in existing_devices:
            print(f"  - {device}")

        # ---------------------------------------------------------------
        # 5. Set Primary Extension
        # ---------------------------------------------------------------
        primary_extension = {
            'pattern': formerly_ext,
            'routePartitionName': HUB_PARTITION
        }

        # ---------------------------------------------------------------
        # 6. Update the user
        # ---------------------------------------------------------------
        service.updateUser(
            userid=OWNER_USER_ID,
            associatedDevices=devices,
            primaryExtension=primary_extension,
            homeCluster=True,
            imAndPresenceEnable=True
        )

        print(
            f"\nDevice {TCT_DEVICE_NAME} associated to user "
            f"{OWNER_USER_ID} successfully."
        )

        print(
            f"Primary extension {formerly_ext} "
            f"assigned to user {OWNER_USER_ID}."
        )

        return True

    except Fault as e:
        print("\nAXL ERROR associating device / updating user:")
        print(e)
        return False

    except Exception as e:
        print("\nERROR preparing user update:")
        print(e)
        return False

# --------------------------------------------------------------------------------------------
# 7. Function to associate an End User with a specific line appearance on a CSF and TCT device
# --------------------------------------------------------------------------------------------


def associate_csf_user_to_line(service, formerly_ext):
    """
    Associate the End User with the specific line appearance
    on the CSF device using the formerly_ext parameter.
    """

    print(
        f"\nAssociating End User {OWNER_USER_ID} "
        f"with line {formerly_ext} on {CSF_DEVICE_NAME}"
    )

    try:
        response = service.updatePhone(
            name=CSF_DEVICE_NAME,
            lines={
                'line': [
                    {
                        'index': 1,

                        'dirn': {
                            'pattern': formerly_ext,
                            'routePartitionName': {
                                '_value_1': HUB_PARTITION
                            }
                        },

                        'associatedEndusers': {
                            'enduser': [
                                {
                                    'userId': OWNER_USER_ID
                                }
                            ]
                        }
                    }
                ]
            }
        )

        print(
            f"End User {OWNER_USER_ID} successfully associated "
            f"with line {formerly_ext} on {CSF_DEVICE_NAME}."
        )

        return True

    except Fault as e:
        print("\nAXL ERROR associating End User with line:")
        print(e)
        return False

    except Exception as e:
        print("\nERROR preparing line association:")
        print(e)
        return False


def associate_tct_user_to_line(service, formerly_ext):
    """
    Associate the End User with the specific line appearance
    on the TCT device using the formerly_ext parameter.
    """

    print(
        f"\nAssociating End User {OWNER_USER_ID} "
        f"with line {formerly_ext} on {TCT_DEVICE_NAME}"
    )

    try:
        response = service.updatePhone(
            name=TCT_DEVICE_NAME,
            lines={
                'line': [
                    {
                        'index': 1,

                        'dirn': {
                            'pattern': formerly_ext,
                            'routePartitionName': {
                                '_value_1': HUB_PARTITION
                            }
                        },

                        'associatedEndusers': {
                            'enduser': [
                                {
                                    'userId': OWNER_USER_ID
                                }
                            ]
                        }
                    }
                ]
            }
        )

        print(
            f"End User {OWNER_USER_ID} successfully associated "
            f"with line {formerly_ext} on {TCT_DEVICE_NAME}."
        )

        return True

    except Fault as e:
        print("\nAXL ERROR associating End User with line:")
        print(e)
        return False

    except Exception as e:
        print("\nERROR preparing line association:")
        print(e)
        return False


# ---------------------------------------------------------------------------------------------#
# ***************************          SERVICENOW FUNCTIONS          ***************************#
# ---------------------------------------------------------------------------------------------#

# ============================================================
# ServiceNow API Helper
# ============================================================

def servicenow_get(endpoint, params=None):
    """
    Perform a GET request against the ServiceNow Table API.
    """

    url = f"{SERVICENOW_URL}{endpoint}"

    headers = {
        "Accept": "application/json"
    }

    response = requests.get(
        url,
        params=params,
        auth=(SERVICENOW_USER, SERVICENOW_PASSWORD),
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    return response.json()

# ============================================================
# 1. Get Active / Approved RITMs
# ============================================================


def get_active_ritms():
    """
    Retrieve active RITMs for the specified catalog item.
    """

    sysparm_query = (
        "active=true"
        "^approval=requested"
        "^order_guide=5726715bdbac4c1033a858b8dc961985"
    )

    params = {
        "sysparm_query": sysparm_query,
        "sysparm_fields": (
            "sys_id,"
            "number,"
            "cat_item,"
            "approval,"
            "order_guide,"
            "state,"
            "stage,"
            "active,"
        ),
        "sysparm_display_value": "true",
        "sysparm_limit": "100"
    }

    endpoint = "/api/now/table/sc_req_item"
    url = f"{SERVICENOW_URL}{endpoint}"
    try:
        response = requests.get(
            url,
            auth=(SERVICENOW_USER, SERVICENOW_PASSWORD),
            headers={
                "Accept": "application/json"
            },
            params=params
        )

        response.raise_for_status()

        data = response.json()

        results = data.get("result", [])
        print(f"RITMs found: {len(results)}")
        print()

        if not results:
            print("No RITMs found.")
            exit(0)
        return results

    except requests.exceptions.RequestException as e:

        print(
            f"ERROR: Unable to retrieve RITMs from ServiceNow: {e}"
        )

        return []

# ============================================================
# 2. Find Cisco Account Setup Task
# ============================================================


def get_cisco_account_setup_task(ritm_sys_id):
    """
    Find the 'Cisco Account Setup' catalog task belonging
    to the specified RITM.
    """

    url = "/api/now/table/sc_task"

    params = {
        "sysparm_query": (
            f"request_item={ritm_sys_id}"
            f"^short_description={CATALOG_TASK_NAME}"
            f"^state!=3"  # Exclude closed tasks
            f"^active=true"  # Only active tasks
        ),

        "sysparm_fields": (
            "sys_id,"
            "number,"
            "short_description,"
            "state,"
            "active,"
            "assignment_group,"
            "request_item"
        ),

        "sysparm_display_value": "true",

        "sysparm_limit": "1"
    }

    try:

        data = servicenow_get(url, params)

        results = data.get("result", [])

        if not results:
            return None

        return results[0]

    except requests.exceptions.RequestException as e:

        print(
            f"ERROR: Unable to retrieve task for RITM "
            f"{ritm_sys_id}: {e}"
        )

        return None

# ============================================================
# 3. Get Employee Variables
# ============================================================


def get_employee_details_from_ritm(ritm_number):
    """
    Read Employee First Name, Employee Last Name, and Employee Location
    from a ServiceNow Requested Item (RITM).

    Example:
        ritm_number = "RITM2432735"

    Returns:
        {
            "first_name": "Pascale",
            "last_name": "Décosse Léger",
            "username": "jdoe",
            "location": "Corporate Office (Mississauga)"
        }

    Returns None if the RITM or required variables cannot be found.
    """

    url = f"{SERVICENOW_URL}/api/now/table/sc_req_item"

    params = {
        "sysparm_query": f"number={ritm_number}",
        "sysparm_fields": (
            "sys_id,"
            "number,"
            f"variables.{SNOW_FIRST_NAME_VARIABLE},"
            f"variables.{SNOW_LAST_NAME_VARIABLE},"
            # f"variables.{SNOW_USERNAME_VARIABLE},"
            f"variables.{SNOW_LOCATION_VARIABLE}"
        ),
        "sysparm_limit": "1",
        "sysparm_display_value": "true"
    }

    headers = {
        "Accept": "application/json"
    }

    try:

        response = requests.get(
            url,
            params=params,
            auth=(SERVICENOW_USER, SERVICENOW_PASSWORD),
            headers=headers,
            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        results = data.get("result", [])

        if not results:
            print(f"ERROR: RITM {ritm_number} was not found.")
            return None

        ritm = results[0]
        print(ritm)
        first_name = ritm.get(
            f"variables.{SNOW_FIRST_NAME_VARIABLE}"
        )

        last_name = ritm.get(
            f"variables.{SNOW_LAST_NAME_VARIABLE}"
        )

        # username = ritm.get(
        #     f"variables.{SNOW_USERNAME_VARIABLE}"
        # )
        username = "t-sallaoua"

        location = ritm.get(
            f"variables.{SNOW_LOCATION_VARIABLE}"
        )

        if not first_name:
            print(
                f"ERROR: First name variable "
                f"'{SNOW_FIRST_NAME_VARIABLE}' is empty."
            )
            return None

        if not username:
            print(
                f"ERROR: Username variable "
                f"'{SNOW_USERNAME_VARIABLE}' is empty."
            )
            return None

        if not last_name:
            print(
                f"ERROR: Last name variable "
                f"'{SNOW_LAST_NAME_VARIABLE}' is empty."
            )
            return None

        if not location:
            print(
                f"ERROR: Location variable "
                f"'{SNOW_LOCATION_VARIABLE}' is empty."
            )
            return None

        return {
            "first_name": first_name,
            "last_name": last_name,
            "username": username,
            "location": location
        }

    except requests.exceptions.HTTPError as e:

        print(
            f"ERROR: ServiceNow HTTP error: "
            f"{response.status_code}"
        )
        print(response.text)

        return None

    except requests.exceptions.RequestException as e:

        print(
            f"ERROR: Unable to connect to ServiceNow: {e}"
        )

        return None

# ============================================================
# Read-only provisioning preflight checks as a Guardrail
# ============================================================


def _axl_fault_means_not_found(error):
    """Return True only for common AXL object-not-found messages."""
    message = str(error).lower()
    return any(token in message for token in (
        "not found", "does not exist", "no such", "unknown device",
        "unknown line", "object does not exist", "was not found"
    ))


def _axl_get_phone_or_none(service, device_name):
    """Read a phone. Return None only when AXL clearly says it is absent."""
    returned_tags = {
        "name": True,
        "description": True,
        "ownerUserName": True,
        "lines": {
            "line": {
                "index": True,
                "dirn": {"pattern": True, "routePartitionName": True},
            }
        },
    }
    try:
        response = service.getPhone(name=device_name, returnedTags=returned_tags)
        returned = response["return"]
        try:
            return returned["phone"]
        except (KeyError, TypeError):
            return getattr(returned, "phone", None)
    except Fault as exc:
        if _axl_fault_means_not_found(exc):
            return None
        raise RuntimeError(f"Unable to verify CUCM device {device_name}: {exc}") from exc


def _get_ad_user_ipphone(username):
    """Read AD ipPhone without modifying AD. Return (DN, current_ipPhone)."""
    username = str(username or "").strip()
    if not username:
        raise RuntimeError("Cannot check AD: employee username is empty.")

    server = Server(AD_SERVER, get_info=ALL, connect_timeout=15)
    connection = None
    try:
        connection = Connection(
            server, user=AD_USER, password=AD_PASSWORD,
            auto_bind=True, receive_timeout=30,
        )
        search_filter = (
            "(&(objectCategory=person)(objectClass=user)"
            f"(sAMAccountName={escape_ldap_filter(username)}))"
        )
        ok = connection.search(
            search_base=AD_SEARCH_BASE,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["sAMAccountName", "ipPhone", "distinguishedName"],
        )
        if not ok:
            raise RuntimeError(f"AD search failed for {username}: {connection.result}")
        if len(connection.entries) == 0:
            raise RuntimeError(f"AD user '{username}' was not found; stopping before changes.")
        if len(connection.entries) > 1:
            raise RuntimeError(f"Multiple AD users matched '{username}'; stopping before changes.")
        user = connection.entries[0]
        value = user["ipPhone"].value
        return user.entry_dn, (str(value).strip() if value is not None else "")
    finally:
        if connection and connection.bound:
            connection.unbind()


def _find_cuc_mailbox(username):
    """Read-only CUC mailbox lookup. Returns None if absent; raises if uncertain."""
    if not CUC_USERNAME or not CUC_PASSWORD or not CUC_ADDRESS:
        raise RuntimeError("CUC connection settings are incomplete; cannot verify mailbox.")

    # CUPI's query parameter filters the users collection by Alias.
    response = cuc_request(
        "GET", "/users", params={"query": f"(alias is {username})"},
        headers={"Accept": "application/json"},
    )
    if response.status_code == 404:
        return None
    if not response.ok:
        raise RuntimeError(
            f"Unable to verify CUC mailbox for '{username}' "
            f"(HTTP {response.status_code}); stopping before changes."
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError("CUC mailbox lookup did not return JSON; cannot safely proceed.") from exc

    # CUPI response wrappers can differ by version/content negotiation. Walk
    # returned objects and match Alias exactly rather than treating an unknown
    # response shape as proof that the mailbox is absent.
    matches = []
    def walk(value):
        if isinstance(value, dict):
            alias = value.get("Alias", value.get("alias"))
            if alias is not None and str(alias).casefold() == username.casefold():
                matches.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(data)

    if len(matches) > 1:
        raise RuntimeError(f"Multiple CUC mailbox records matched '{username}'; stopping before changes.")
    if len(matches) == 1:
        return matches[0]

    # A successful response with a recognizable empty users collection means absent.
    if isinstance(data, dict) and any(key in data for key in ("@total", "User", "Users", "users")):
        return None
    if isinstance(data, list) and not data:
        return None
    raise RuntimeError(
        f"CUC returned HTTP {response.status_code}, but the mailbox response shape "
        "was not recognized. Stopping rather than assuming the mailbox is absent."
    )


def preflight_employee_state(service, employee_details, extension):
    """Inspect all target systems before any CUCM/AD/CUC provisioning writes.

    Safe policy: the selected DN must still be an unused FORMERLY HUB line;
    CSF/TCT must not already exist; the CUCM end user must exist; existing
    device associations must not conflict; AD ipPhone must be empty or already
    equal to the selected extension; and any existing CUC mailbox must have
    the same DTMF access ID. Existing CSF/TCT devices are intentionally not
    auto-updated: partial prior provisioning requires review/reconciliation.
    """
    username = str(employee_details.get("username") or "").strip()
    if not username:
        raise RuntimeError("Employee username is empty; cannot run preflight.")

    csf_name = "CSF" + username.upper().replace("-", "").replace("_", "")
    tct_name = "TCT" + username.upper().replace("-", "").replace("_", "")
    report = {"cuc_mailbox_exists": False}
    conflicts = []

    print("\n========== READ-ONLY PROVISIONING PREFLIGHT ==========")
    print(f"Username: {username}")
    print(f"Candidate DN: {extension} / {HUB_PARTITION}")
    print(f"CSF device: {csf_name}")
    print(f"TCT device: {tct_name}")

    # 1. DN: it is expected to exist as a spare line, but it must still be marked unused.
    try:
        line_response = service.getLine(
            pattern=extension,
            routePartitionName=HUB_PARTITION,
            returnedTags={"pattern": True, "description": True, "routePartitionName": True},
        )
        returned = line_response["return"]
        try:
            line = returned["line"]
        except (KeyError, TypeError):
            line = getattr(returned, "line", None)
    except Fault as exc:
        raise RuntimeError(f"Unable to verify candidate DN {extension}: {exc}") from exc
    if not line:
        conflicts.append(f"DN {extension} was not returned by getLine; refusing to provision.")
    else:
        description = getattr(line, "description", None)
        actual_pattern = str(getattr(line, "pattern", "") or "")
        print(f"DN check: found pattern={actual_pattern}, description={description!r}")
        if actual_pattern != str(extension) or description != "FORMERLY HUB":
            conflicts.append(
                f"DN {extension} is not a confirmed FORMERLY HUB spare (description={description!r})."
            )

    # 2. CSF and TCT: never overwrite/adopt a device automatically on a new run.
    csf = _axl_get_phone_or_none(service, csf_name)
    tct = _axl_get_phone_or_none(service, tct_name)
    report["csf_exists"] = csf is not None
    report["tct_exists"] = tct is not None
    print(f"CSF check: {'EXISTS' if csf is not None else 'absent'}")
    print(f"TCT check: {'EXISTS' if tct is not None else 'absent'}")
    if csf is not None:
        conflicts.append(f"CUCM device {csf_name} already exists; refusing to modify it automatically.")
    if tct is not None:
        conflicts.append(f"CUCM device {tct_name} already exists; refusing to modify it automatically.")

    # 3. CUCM end-user and current device associations.
    try:
        user_response = service.getUser(userid=username)
        returned = user_response["return"]
        try:
            user = returned["user"]
        except (KeyError, TypeError):
            user = getattr(returned, "user", None)
    except Fault as exc:
        raise RuntimeError(f"Unable to verify CUCM end user '{username}': {exc}") from exc
    if not user:
        conflicts.append(f"CUCM end user '{username}' was not returned; refusing to provision.")
        associated_devices = []
    else:
        associated = getattr(user, "associatedDevices", None)
        associated_devices = list(getattr(associated, "device", []) or []) if associated else []
    report["associated_devices"] = associated_devices
    print(f"CUCM user check: {'found' if user else 'NOT FOUND'}")
    print(f"Existing associated devices: {associated_devices}")
    primary = getattr(user, "primaryExtension", None) if user else None
    primary_pattern = getattr(primary, "pattern", None) if primary else None
    primary_partition = getattr(primary, "routePartitionName", None) if primary else None
    report["primary_extension"] = {
        "pattern": primary_pattern,
        "routePartitionName": primary_partition,
    }
    print(f"Existing primary extension: {primary_pattern!r} / {primary_partition!r}")
    if primary_pattern and not (
        str(primary_pattern) == str(extension)
        and str(primary_partition or "") == HUB_PARTITION
    ):
        conflicts.append(
            f"CUCM user '{username}' already has primary extension "
            f"{primary_pattern} / {primary_partition}; refusing to overwrite it."
        )
    for device_name in (csf_name, tct_name):
        if device_name in associated_devices:
            conflicts.append(
                f"CUCM user '{username}' already has {device_name} associated; refusing automatic changes."
            )

    # 4. AD ipPhone must be empty or already match this extension.
    # ad_dn, current_ipphone = _get_ad_user_ipphone(username)
    # report["ad_ipphone"] = current_ipphone
    # print(f"AD check: {ad_dn}; ipPhone={current_ipphone or '(empty)'}")
    # if current_ipphone and current_ipphone != str(extension):
    #     conflicts.append(
    #         f"AD ipPhone is already '{current_ipphone}', not selected DN '{extension}'."
    #     )

    # 5. CUC mailbox must be absent or match the selected extension.
    mailbox = _find_cuc_mailbox(username)
    report["cuc_mailbox_exists"] = mailbox is not None
    report["cuc_mailbox"] = mailbox
    if mailbox is None:
        print("CUC mailbox check: absent")
    else:
        dtmf = mailbox.get("DtmfAccessId", mailbox.get("dtmfAccessId", ""))
        print(f"CUC mailbox check: exists; DtmfAccessId={dtmf!r}")
        if str(dtmf or "").strip() != str(extension):
            conflicts.append(
                f"CUC mailbox '{username}' already exists with DtmfAccessId={dtmf!r}, "
                f"not '{extension}'."
            )

    print("=====================================================")
    if conflicts:
        global LAST_CUCM_FAILURE_DETAILS
        LAST_CUCM_FAILURE_DETAILS = list(conflicts)
        print("PREFLIGHT FAILED — no CUCM, AD, or CUC provisioning writes will be attempted:")
        for conflict in conflicts:
            print(f" - {conflict}")
        return None

    print("PREFLIGHT PASSED — no conflicting objects detected.")
    return report


# ============================================================
# 4. CUCM Processing based on ServiceNow request variables
# ============================================================


def process_cucm(employee_details):
    """
    Process the CUCM configuration for the given employee.
    """
    global CSF_DEVICE_NAME, TCT_DEVICE_NAME, OWNER_USER_ID

    try:

        first_name = employee_details["first_name"]
        last_name = employee_details["last_name"]
        username = employee_details["username"]

        global CSF_DEVICE_NAME, TCT_DEVICE_NAME, OWNER_USER_ID
        global DISPLAY_NAME, DISPLAY_ASCII, DESCRIPTION
        global ALERTING_NAME, ASCII_ALERTING_NAME
        # In case the username contains hyphens or underscores, remove them for device naming
        CSF_DEVICE_NAME = 'CSF' + username.upper().replace('-', '').replace('_', '')
        TCT_DEVICE_NAME = 'TCT' + username.upper().replace('-', '').replace('_', '')
        OWNER_USER_ID = username

        DISPLAY_NAME = f"{first_name} {last_name}"
        DISPLAY_ASCII = DISPLAY_NAME
        DESCRIPTION = f"HUB - {first_name} {last_name}"
        ALERTING_NAME = DISPLAY_NAME
        ASCII_ALERTING_NAME = DISPLAY_NAME

        print()
        print("===== Sending Data to CUCM =====")
        print(f"FIRST_NAME = {first_name}")
        print(f"LAST_NAME  = {last_name}")
        print(f"USERNAME   = {username}")

        service = get_axl_client()
        # 1. Find the lowest available FORMERLY HUB extension
        formerly_ext = find_formerly_extension(service)

        if not formerly_ext:
            print("ERROR: No available FORMERLY HUB extension found.")
            return

        print(f"Selected FORMERLY_EXT = {formerly_ext}")

        # Read-only checks across CUCM, AD, and CUC BEFORE any provisioning writes.
        preflight = preflight_employee_state(service, employee_details, formerly_ext)
        if preflight is None:
            print("Stopping because the read-only preflight found a conflict.")
            return None

        # Store the selected extension and preflight state for downstream steps.
        cucm_output = employee_details.copy()
        cucm_output['formerly_ext'] = formerly_ext
        cucm_output['cuc_mailbox_exists'] = preflight['cuc_mailbox_exists']

        # 2. Create CSF and associate the formerly_ext DN
        if not create_csf_phone(service, formerly_ext):
            print("\nStopping automation because CSF creation failed.")
            return

        if not create_tct_phone(service, formerly_ext):
            print("\nStopping automation because TCT creation failed.")
            return

         # 3. Update DN-level configuration
        if not update_line(service, formerly_ext):
            print("\nStopping automation because DN update failed.")
            return

        # 4. Associate device to user
        if not associate_csf_device_to_user(service, formerly_ext):
            print("\nStopping automation because device association failed.")
            return

        if not associate_tct_device_to_user(service, formerly_ext):
            print("\nStopping automation because device association failed.")
            return

        # 5. Associate End User with the specific line appearance
        if not associate_csf_user_to_line(service, formerly_ext):
            print("\nStopping automation because line-user association failed.")
            return

        if not associate_tct_user_to_line(service, formerly_ext):
            print("\nStopping automation because line-user association failed.")
            return

        return cucm_output
    
    except Exception as e:
        print(f"Error processing CUCM for employee: {e}")
        return None

# ============================================================
# 5. Update Active Directory 'IP phone' field for a user
# ============================================================


def update_ad_ipphone(username, extension):
    """
    Update the ipPhone attribute for an existing AD user.

    username: AD sAMAccountName
    extension: Value to write to the ipPhone attribute
    """

    username = str(username).strip()
    extension = str(extension).strip()

    if not username or not extension:
        raise ValueError("Username and extension are required.")

    if not extension.isdigit():
        raise ValueError(f"Invalid extension: {extension}")

    if not all([
        AD_SERVER,
        AD_USER,
        AD_PASSWORD,
        AD_SEARCH_BASE,
    ]):
        raise ValueError("Missing required AD configuration in .env.")

    server = Server(
        AD_SERVER,
        get_info=ALL,
        connect_timeout=15,
    )

    connection = None

    try:
        connection = Connection(
            server,
            user=AD_USER,
            password=AD_PASSWORD,
            auto_bind=True,
            receive_timeout=30,
        )

        print(f"Connected to Active Directory: {AD_SERVER}")

        # Locate the existing user by sAMAccountName.
        search_filter = (
            "(&(objectCategory=person)"
            "(objectClass=user)"
            f"(sAMAccountName={escape_ldap_filter(username)}))"
        )

        connection.search(
            search_base=AD_SEARCH_BASE,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=["sAMAccountName", "ipPhone", "distinguishedName"],
        )

        if len(connection.entries) == 0:
            print(f"FAILED: AD user '{username}' was not found.")
            return False

        if len(connection.entries) > 1:
            print(f"FAILED: Multiple AD users matched '{username}'.")
            return False

        user = connection.entries[0]
        current_value = (
            str(user["ipPhone"].value)
            if user["ipPhone"].value is not None
            else ""
        )

        print(f"AD user: {user.entry_dn}")
        print(f"Current ipPhone: {current_value or '(empty)'}")
        print(f"New ipPhone: {extension}")

        # Avoid unnecessary modifications.
        if current_value == extension:
            print("No change needed; ipPhone already matches.")
            return True

        # Update only the ipPhone attribute.
        success = connection.modify(
            user.entry_dn,
            {
                "ipPhone": [(2, [extension])]
            },
        )

        if success:
            print(
                f"SUCCESS: Updated ipPhone for '{username}' "
                f"to '{extension}'."
            )
            return True

        print("FAILED: Active Directory rejected the modification.")
        print("LDAP result:", connection.result)
        return False

    finally:
        if connection and connection.bound:
            connection.unbind()

def escape_ldap_filter(value):
    """Escape special characters in an LDAP search-filter value."""
    return (
        value.replace("\\", r"\5c")
        .replace("*", r"\2a")
        .replace("(", r"\28")
        .replace(")", r"\29")
        .replace("\x00", r"\00")
    )


# ============================================================
# 6. Function to Pause the script for 20 minutes
# ============================================================

def pause_script_for_20_minutes():
    """
    Pause the script for 20 minutes.
    """
    print("Pausing the script for 20 minutes...")
    # sleep(20 * 60)  # 20 minutes in seconds
    # Five seconds for testing purposes
    sleep(5)
    print("Resuming the script after 20 minutes.")
    print()


# ============================================================
# 7. Cisco Unity Connection add Voice Mail to end users
# ============================================================

def cuc_request(method, endpoint, **kwargs):
    """Send a CUPI request and print diagnostic details on failure."""
    session = requests.Session()
    session.auth = HTTPBasicAuth(CUC_USERNAME or "", CUC_PASSWORD or "")
    session.headers.update({"Accept": "application/json"})
    session.verify = False
    
    url = f"{CUC_ADDRESS}/{endpoint.lstrip('/')}"

    response = session.request(
        method,
        url,
        timeout=30,
        **kwargs,
    )

    print(f"\n{method} {response.url}")
    print(f"HTTP status: {response.status_code}")

    if not response.ok:
        print("CUC response body:")
        print(response.text[:5000])

    return response

def create_cuc_mailbox(username, extension):
    print("\n========== TEST 4: CREATE MAILBOX ==========")

    payload = {
        "Alias": username,
        "DtmfAccessId": extension,
    }

    print(f"Username: {username}")
    print(f"Extension: {extension}")
    print(f"Template alias: {CUC_TEMPLATE}")
    print(f"Payload: {payload}")

    response = cuc_request(
        "POST",
        "/users",
        params={"templateAlias": CUC_TEMPLATE},
        json=payload,
        headers={"Content-Type": "application/json"},
    )

    if response.status_code in (200, 201):
        print("SUCCESS: CUC accepted the mailbox creation request.")
        print("Location header:", response.headers.get("Location"))
        print("Response body:", response.text[:2000])
        return True

    print("FAILED: Mailbox creation was rejected.")
    print("Use the response body above to diagnose the issue.")
    return False

# ===================================================================================
# 8. Update ServiceNow Catalog Task, Close or Re-assign based on provisioning result
# ===================================================================================

# This Function  updates the work notes of a servicenow catalog task ONLY
def update_catalog_task_work_notes_only(task_sys_id, work_notes):
    url = f"/api/now/table/sc_task/{task_sys_id}"

    payload = {
        "work_notes": work_notes
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:

        response = requests.put(
            SERVICENOW_URL + url,
            auth=(SERVICENOW_USER, SERVICENOW_PASSWORD),
            headers=headers,
            json=payload,
            timeout=30
        )

        response.raise_for_status()

        print(
            f"ServiceNow task {task_sys_id} work notes updated successfully."
        )

        return True

    except requests.exceptions.RequestException as e:

        print(
            f"ERROR: Unable to update work notes for ServiceNow task "
            f"{task_sys_id}: {e}"
        )
        return False

# This Function updates the Work notes and Close the task
def update_catalog_task_work_notes_and_close(task_sys_id, work_notes):
    url = f"/api/now/table/sc_task/{task_sys_id}"

    payload = {
        "work_notes": work_notes,
        "state": "3"  # Close the task
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:

        response = requests.put(
            SERVICENOW_URL + url,
            auth=(SERVICENOW_USER, SERVICENOW_PASSWORD),
            headers=headers,
            json=payload,
            timeout=30
        )

        response.raise_for_status()

        print(
            f"ServiceNow task {task_sys_id} work notes updated and task closed successfully."
        )

        return True

    except requests.exceptions.RequestException as e:

        print(
            f"ERROR: Unable to update work notes and close ServiceNow task "
            f"{task_sys_id}: {e}"
        )
        return False

# This Function updates the work notes and reassign the case to the UC Team
def update_catalog_task_work_notes_and_reassign_to_uc_team(task_sys_id, work_notes):
    url = f"/api/now/table/sc_task/{task_sys_id}"

    payload = {
        "work_notes": work_notes,
        "assignment_group": UC_ASSIGNMENT_GROUP_SYS_ID,
    }

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:

        response = requests.put(
            SERVICENOW_URL + url,
            auth=(SERVICENOW_USER, SERVICENOW_PASSWORD),
            headers=headers,
            json=payload,
            timeout=30
        )

        response.raise_for_status()

        print(
            f"ServiceNow task {task_sys_id} work notes updated and reassigned to UC Team successfully."
        )

        return True

    except requests.exceptions.RequestException as e:

        print(
            f"ERROR: Unable to update work notes and reassign ServiceNow task "
            f"{task_sys_id}: {e}"
        )
        return False

# ============================================================
#                          Main Function
# ============================================================
def main():
    try:
        # 1. Get Active / Approved RITMs
        active_ritms = get_active_ritms()

        print(f"RITMs found: {len(active_ritms)}")
        print()
        if not active_ritms:

            print("No RITMs found.")
            exit(0)

        # 2. Loop through each active RITM and display its details and pull only the tasks that match the Cisco Account Setup Task
        # Start of active_ritms loop
        for ritm in active_ritms:
            # 2.a. Display the details of the current RITM
            # print("================================================")
            # print("Sys ID       :", ritm.get("sys_id"))
            # print("Number       :", ritm.get("number"))
            # print("Catalog Item :", ritm.get("cat_item"))
            # print("Active       :", ritm.get("active"))
            # print("Approval     :", ritm.get("approval"))
            # print("State        :", ritm.get("state"))
            # print("Stage        :", ritm.get("stage"))
            # print("================================================")

            # 2.b. Get only the Cisco Account Task in the current RITM
            cisco_task = get_cisco_account_setup_task(ritm.get("sys_id"))
            print("Cisco Account Setup Search for only active and open tasks")
            print("---------------------------------------------------------")
            # Step 1.Print the details of the Cisco Account Setup Task if it only exist and open and active state
            if cisco_task and cisco_task.get("state") != "3" and cisco_task.get("active") == "true":
                print(f"Task {cisco_task.get('number')} is open and active.")
                print()
                print(f"Task Number       : {cisco_task.get('number')}")
                print(f"Task Sys ID       : {cisco_task.get('sys_id')}")
                print(f"Short Description : {cisco_task.get('short_description')}")
                print(f"State             : {cisco_task.get('state')}")
                print(f"Active            : {cisco_task.get('active')}")
                print(f"Assignment Group  : {cisco_task.get('assignment_group')['display_value']}")
                print(f"Request Item      : {cisco_task.get('request_item')['display_value']}")
                print(f"Order Guide       : {ritm.get('order_guide')['display_value']}")

                # 2.b.1. Pull the employee details
                ritm_number = ritm.get("number")
                employee_details = get_employee_details_from_ritm(ritm_number)
                print(employee_details)
                if employee_details:
                    print()
                    print("Processing Employee Details.........")
                    print("Employee Variables")
                    print("-------------------")
                    print(f"RITM       : {ritm_number}")
                    print(f"First Name : {employee_details['first_name']}")
                    print(f"Last Name  : {employee_details['last_name']}")
                    print(f"Username   : {employee_details['username']}")
                    print(f"Location   : {employee_details['location']}")
                    # 2.b.1.a. Do CallManger Processing
                    print("Processing CUCM Function - adding devices........")
                    cucm_processed_employee = process_cucm(employee_details)
                    if cucm_processed_employee:
                        normalized_username = cucm_processed_employee['username'].upper().replace('-', '').replace('_', '')
                        csf_device_name = 'CSF' + normalized_username
                        tct_device_name = 'TCT' + normalized_username
                        print("\n============================================")
                        print("Phone CSF and TCT provisioning complete")
                        print("==============================================")
                        print("\n")
                        print("====================================================")
                        print("===== USER PROVISIONING COMPLETED SUCCESSFULLY =====")
                        print("====================================================")
                        print(
                            f"Username       : {employee_details['username']}")
                        print(
                            f"Extension      : {cucm_processed_employee['formerly_ext']}")
                        print(
                            f"Device         : {csf_device_name.upper()} / {tct_device_name.upper()}")
                        print("====================================================")

                        # 2.b.1.a.1 Update Active Directory Process
                        print("Processing AD Employee Details.........")
                        ad_success = update_ad_ipphone(
                            cucm_processed_employee['username'], cucm_processed_employee['formerly_ext'])
                        if not ad_success:
                            print("Active Directory update failed.")
                            update_catalog_task_work_notes_and_reassign_to_uc_team(
                            cisco_task['sys_id'], work_notes="Active Directory update failed. reassigning to UC team.")
                            continue
        
                        # 2.b.1.a.2 / 2.b.1.a.3: create CUC mailbox only if preflight
                        # confirmed it is absent. A matching existing mailbox is left untouched.
                        if cucm_processed_employee.get('cuc_mailbox_exists'):
                            print("Matching CUC mailbox already exists; skipping mailbox creation.")
                            cuc_success = True
                        else:
                            print("Pausing script for 20 minutes...")
                            pause_script_for_20_minutes()
                            print("Starting Cisco Unity Connection processing...")
                            cuc_success = create_cuc_mailbox(
                                cucm_processed_employee['username'],
                                cucm_processed_employee['formerly_ext'])
                        if not cuc_success:
                            print(
                                "Cisco Unity Connection Voicemail processing failed.")
                            update_catalog_task_work_notes_and_reassign_to_uc_team(
                                cisco_task['sys_id'], work_notes="Cisco Unity Connection Voicemail processing failed. reassigning to UC team.")
                            continue
                        
                        # 2.b.1.a.4  Update Cisco Account Setup Task and close it
                        print("Updating Cisco Account Setup Task and closing it...")
                        work_notes = (
                            "Cisco Account Setup completed successfully "
                            "by MACD automation.\n\n"
                            f"Employee: {cucm_processed_employee['first_name']} "
                            f"{cucm_processed_employee['last_name']}\n"
                            f"Username: {cucm_processed_employee['username']}\n"
                            f"Location: {cucm_processed_employee['location']}\n"
                            f"Extension: {cucm_processed_employee['formerly_ext']}\n"
                            "Call Manager and Unity Connection provisioning completed successfully!\n"
                            f"Closing Cisco Account Setup Task.\n"
                        )
                        task_closed = update_catalog_task_work_notes_and_close(
                            cisco_task['sys_id'], work_notes)
                        if not task_closed:
                            print("WARNING: Provisioning succeeded, but the ServiceNow task was not closed.")

                    else:
                        # CUCM provisioning failed — capture the reason and reassign the task.
                        print()
                        print(f"ERROR: CUCM processing failed for RITM {ritm_number}")
                        print("Reassigning the task to the UC team for investigation.")

                        # Retrieve detailed errors captured by the preflight checks.
                        failure_details = LAST_CUCM_FAILURE_DETAILS or [
                            "No detailed failure reason was captured."
                        ]

                        # Print the detailed failure reason to the console.
                        print()
                        print("=====================================================")
                        print("CUCM / PREFLIGHT FAILURE DETAILS")
                        print("=====================================================")

                        for conflict in failure_details:
                            print(f" - {conflict}")

                        print("=====================================================")

                        # Build ServiceNow work notes with the same failure details.
                        work_notes = (
                            "CUCM provisioning failed. "
                            "Reassigned to the UC team for investigation.\n\n"
                            "Preflight / failure details:\n"
                            + "\n".join(f" - {conflict}" for conflict in failure_details)
                            + "\n\n"
                            f"Employee: {employee_details['first_name']} "
                            f"{employee_details['last_name']}\n"
                            f"Username: {employee_details['username']}\n"
                            f"Location: {employee_details['location']}\n"
                            f"RITM: {ritm_number}\n"
                        )

                        # Reassign the task and save the work notes.
                        update_catalog_task_work_notes_and_reassign_to_uc_team(
                            cisco_task['sys_id'],
                            work_notes
                        )

                        continue

                else:
                    print()
                    print("Employee Variables")
                    print("--------------------------------")
                    print(f"No employee details found for RITM {ritm_number}.")
                print("================================================")
                # Break out of the loop after handling the current RITM for testing purposes
                print("Breaking out of the RITMs loop for testing purposes.")
                # break
            # End of if cisco_task check
            else:
                print(
                    f"No task with short description '{CATALOG_TASK_NAME}' was found for RITM {ritm.get('number')}")
                # Continue to the next RITM since no Cisco Account Setup Task was found
                continue
            # End of the Else condition
        # End of active_ritms loop
    # End of the try processing
    except requests.exceptions.RequestException as e:
        print(f"ERROR: {e}")
        exit(1)
    # End of the try-except block

# End of the Main Function

    print("Automation completed.")


# ---------------------------------------------------------------------------
# Entry point for the script
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    main()
