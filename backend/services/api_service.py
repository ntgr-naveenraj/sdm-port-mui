"""
Real API Service - Extracted from original sdm_manager_gui.py
100% EXACT logic for InsightCloudAPI - no dummy data
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from typing import List, Optional

logger = logging.getLogger(__name__)


def _insight_device_ip(device_data: dict) -> str:
    """
    LAN/management IP from Insight deviceList payload.
    Original GUI (sdm_manager_gui.APDevice): ipSettings first, then ipAddress.
    """
    v = device_data.get("ipSettings", device_data.get("ipAddress", ""))
    if isinstance(v, dict):
        inner = v.get("ipAddress") or v.get("ip") or v.get("ipv4") or v.get("ipv4Addr")
        return str(inner).strip() if inner is not None else ""
    if v is None:
        return ""
    return str(v).strip()


@dataclass
class Organization:
    org_id: str
    org_name: str
    location_count: int
    device_count: int


@dataclass
class Location:
    network_id: str
    network_name: str
    device_count: int
    ap_count: int


@dataclass
class APDevice:
    device_id: str
    serial_no: str
    name: str
    model: str
    ip_address: str
    mac_address: str
    network_id: str
    network_name: str
    device_status: int
    last_seen: int
    org_id: Optional[str] = None
    org_name: Optional[str] = None


class APIService:
    """
    REAL API Service - 100% EXACT from original (lines 423-779)
    Calls actual Insight Cloud API endpoints
    """
    
    def __init__(self, api_base_url: str, api_key: str, web_url: str):
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.web_url = web_url
        logger.info(f"APIService initialized for: {api_base_url}")

    def _get_headers(self, user_id: str, account_id: str, token: str, **kwargs) -> dict:
        """
        Get request headers - EXACT from original lines 471-489
        """
        # Clean token in case it comes from cookie format (EXACT FROM ORIGINAL)
        clean_token = token
        if "accessToken=" in token:
            clean_token = token.split("accessToken=")[1].split(";")[0]
        
        headers = {
            "apiKey": self.api_key,     
            "accountId": account_id,      
            "token": clean_token,
            "content-type": "application/json",
            "accept": "application/json, text/plain, */*",
            "origin": self.web_url,
            "referer": f"{self.web_url}/"
        }
        # Add networkid header for device APIs (EXACT FROM ORIGINAL)
        if "networkid" in kwargs:
            headers["networkid"] = kwargs["networkid"]
        return headers

    def get_organizations_sync(self, user_id: str, account_id: str, token: str) -> List[Organization]:
        """
        Get organizations - REAL endpoint (line 543-563)
        Endpoint: GET organization/v1/orgInfo/{user_id}
        """
        import requests
        import certifi
        
        try:
            logger.info(f"Fetching organizations for user {user_id}")
            logger.info(f"Using API base URL: {self.api_base_url}")
            
            endpoint = f"organization/v1/orgInfo/{user_id}"
            url = self.api_base_url + endpoint
            headers = self._get_headers(user_id, account_id, token)
            
            logger.info(f"GET {url}")
            
            # REAL HTTP call to Insight Cloud API (EXACT FROM ORIGINAL)
            response = requests.get(
                url,
                headers=headers,
                timeout=30,
                verify=certifi.where()
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Organizations response: {result}")
                
                # Parse response (EXACT FROM ORIGINAL lines 552-559)
                if result.get("response", {}).get("status"):
                    orgs = []
                    for org_data in result.get("details", []):
                        org = Organization(
                            org_id=org_data.get("orgId", ""),
                            org_name=org_data.get("orgName", ""),
                            location_count=org_data.get("locationCount", 0),
                            device_count=org_data.get("deviceCount", 0)
                        )
                        orgs.append(org)
                    
                    logger.info(f"Successfully fetched {len(orgs)} organizations")
                    return orgs
                else:
                    error_msg = result.get("response", {}).get("message", "Failed to fetch organizations")
                    logger.error(f"API error: {error_msg}")
                    return []
            else:
                logger.error(f"API returned status {response.status_code}")
                return []
                    
        except Exception as e:
            logger.exception(f"Failed to fetch organizations: {str(e)}")
            return []

    def verify_session_credentials_sync(
        self, user_id: str, account_id: str, token: str
    ) -> tuple[bool, str]:
        """
        Validate browser session tokens with a real Insight call (organization/v1/orgInfo).
        Used for Manual Credentials login — same headers as Swagger-authenticated API calls.
        """
        import requests
        import certifi

        try:
            endpoint = f"organization/v1/orgInfo/{user_id}"
            url = self.api_base_url + endpoint
            headers = self._get_headers(user_id, account_id, token)
            response = requests.get(
                url, headers=headers, timeout=30, verify=certifi.where()
            )
            if response.status_code != 200:
                return False, f"Insight returned HTTP {response.status_code}"
            result = response.json()
            if result.get("response", {}).get("status"):
                return True, ""
            msg = result.get("response", {}).get("message", "Session rejected by Insight")
            return False, str(msg)
        except Exception as e:
            logger.exception("Session verification failed")
            return False, str(e)

    def get_user_profile_email_sync(
        self, user_id: str, account_id: str, token: str
    ) -> Optional[str]:
        """
        GET user/v1/userProfile — Insight returns { status, meta: { userInfo: { email } } }.
        Requires header userId (Insight UserController); same token/apiKey/accountId as orgInfo.
        """
        import requests
        import certifi

        try:
            url = self.api_base_url + "user/v1/userProfile"
            headers = dict(self._get_headers(user_id, account_id, token))
            headers["userId"] = user_id
            response = requests.get(
                url, headers=headers, timeout=30, verify=certifi.where()
            )
            if response.status_code != 200:
                logger.warning(
                    "userProfile: HTTP %s for user %s",
                    response.status_code,
                    user_id,
                )
                return None
            data = response.json()
            if not data.get("status"):
                logger.warning("userProfile: status=false in body")
                return None
            meta = data.get("meta") or {}
            user_info = meta.get("userInfo") or meta.get("userinfo")
            if not isinstance(user_info, dict):
                return None
            email = (user_info.get("email") or "").strip()
            return email or None
        except Exception:
            logger.exception("userProfile fetch failed")
            return None

    def get_locations_sync(self, user_id: str, account_id: str, token: str, org_id: str) -> List[Location]:
        """
        Get locations - REAL endpoint (line 566-617)
        Endpoint: PUT network/v1/locationGridDetails/{user_id}/{org_id}/0
        NOTE: This is PUT, not GET!
        """
        import requests
        import certifi
        
        try:
            logger.info(f"Fetching locations for user {user_id}, org {org_id}")
            
            # EXACT endpoint from original (line 571)
            endpoint = f"network/v1/locationGridDetails/{user_id}/{org_id}/0"
            url = self.api_base_url + endpoint
            headers = self._get_headers(user_id, account_id, token)
            
            logger.info(f"PUT {url}")
            
            # REAL HTTP call - NOTE: PUT method not GET! (EXACT FROM ORIGINAL)
            response = requests.put(
                url,
                json={},  # Empty body (EXACT FROM ORIGINAL line 575)
                headers=headers,
                timeout=30,
                verify=certifi.where()
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Locations response: {result}")
                
                # Parse response (EXACT FROM ORIGINAL lines 581-617)
                if result.get("response", {}).get("status"):
                    location_info = result.get("info", [])  # Note: "info" not "details"!
                    
                    if location_info:
                        logger.info(f"Found {len(location_info)} locations")
                        
                        locations = []
                        for loc_data in location_info:
                            # Data mapping (EXACT FROM ORIGINAL)
                            location = Location(
                                network_id=loc_data.get("networkId", ""),
                                network_name=loc_data.get("networkName", ""),
                                device_count=loc_data.get("totalDevice", 0),
                                ap_count=loc_data.get("totalDevice", 0)
                            )
                            locations.append(location)
                            logger.info(f"  - {location.network_name}")
                        
                        return locations
                    else:
                        logger.warning("No location details found")
                        return []
                else:
                    error_msg = result.get("response", {}).get("message", "Unknown error")
                    logger.error(f"API error: {error_msg}")
                    return []
            else:
                logger.error(f"API returned status {response.status_code}")
                return []
            
        except Exception as e:
            logger.exception(f"Failed to fetch locations: {str(e)}")
            return []

    def get_ap_devices_sync(self, user_id: str, account_id: str, token: str, network_id: str) -> List[APDevice]:
        """
        Get AP devices - REAL endpoint (line 620-679)
        Endpoint: PUT device/v1/deviceList/{user_id}/{network_id}/0
        """
        import requests
        import certifi
        
        try:
            logger.info(f"Fetching AP devices for network {network_id}")
            
            # EXACT endpoint from original (line 625)
            endpoint = f"device/v1/deviceList/{user_id}/{network_id}/0"
            url = self.api_base_url + endpoint
            headers = self._get_headers(user_id, account_id, token, networkid=network_id)
            
            logger.info(f"PUT {url}")
            
            # REAL HTTP call (EXACT FROM ORIGINAL)
            response = requests.put(
                url,
                json={},
                headers=headers,
                timeout=30,
                verify=certifi.where()
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Device API response: {result}")
                
                # Parse response (EXACT FROM ORIGINAL lines 634-679)
                if result.get("response", {}).get("status"):
                    details = result.get("details", {})
                    devices_data = details.get("data", []) if isinstance(details, dict) else []
                    
                    if devices_data:
                        logger.info(f"Found {len(devices_data)} devices")
                        
                        ap_devices = []
                        for device_data in devices_data:
                            # Filter for AP devices (EXACT FROM ORIGINAL)
                            if not isinstance(device_data, dict):
                                continue
                            
                            device_type = device_data.get("deviceType", "").upper()
                            if device_type == "AP":
                                device = APDevice(
                                    device_id=device_data.get("deviceId", ""),
                                    serial_no=device_data.get("serialNo", ""),
                                    name=device_data.get("deviceName", ""),
                                    model=device_data.get("model", ""),
                                    ip_address=_insight_device_ip(device_data),
                                    mac_address=device_data.get("macAddress", ""),
                                    network_id=device_data.get("networkId", ""),
                                    network_name=device_data.get("networkName", ""),
                                    device_status=device_data.get("deviceStatus", 0),
                                    last_seen=device_data.get("lastSeen", 0)
                                )
                                ap_devices.append(device)
                                logger.info(f"  - {device.name}")
                        
                        if ap_devices:
                            logger.info(f"SUCCESS: Found {len(ap_devices)} AP devices")
                            return ap_devices
                        else:
                            logger.warning("No AP devices found in response")
                            return []
                    else:
                        logger.warning("No devices found in response")
                        return []
                else:
                    error_msg = result.get("response", {}).get("message", "Unknown error")
                    logger.error(f"API error: {error_msg}")
                    return []
                
            else:
                logger.error(f"API returned status {response.status_code}")
                return []
                
        except Exception as e:
            logger.exception(f"Failed to fetch devices: {str(e)}")
            return []

    def get_ap_devices_for_org_sync(
        self,
        user_id: str,
        account_id: str,
        token: str,
        org_id: str,
        org_name: Optional[str] = None,
    ) -> List[APDevice]:
        """
        All AP devices for an organization: locationGridDetails then deviceList per network
        (Insight device/v1/deviceList/{user_id}/{network_id}/0; AP-only filter in get_ap_devices_sync).
        """
        locations = self.get_locations_sync(user_id, account_id, token, org_id)
        if not locations:
            return []
        on = org_name or ""
        merged: List[APDevice] = []
        max_workers = min(12, max(1, len(locations)))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self.get_ap_devices_sync, user_id, account_id, token, loc.network_id): loc
                for loc in locations
            }
            for fut in as_completed(futures):
                loc = futures[fut]
                try:
                    for d in fut.result():
                        merged.append(replace(d, org_id=org_id, org_name=on or None))
                except Exception:
                    logger.exception("AP device list failed for network %s", loc.network_id)
        return merged

    def get_ap_devices_all_orgs_sync(self, user_id: str, account_id: str, token: str) -> List[APDevice]:
        """AP devices across every organization for the account."""
        orgs = self.get_organizations_sync(user_id, account_id, token)
        if not orgs:
            return []
        merged: List[APDevice] = []
        max_workers = min(6, max(1, len(orgs)))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(
                    self.get_ap_devices_for_org_sync,
                    user_id,
                    account_id,
                    token,
                    o.org_id,
                    o.org_name,
                ): o
                for o in orgs
            }
            for fut in as_completed(futures):
                try:
                    merged.extend(fut.result())
                except Exception:
                    logger.exception("AP aggregate failed for an organization")
        return merged
