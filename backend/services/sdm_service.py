"""
Real SDM Service - Extracted from original sdm_manager_gui.py
100% EXACT logic for SDM operations - no dummy data
"""

import logging
from dataclasses import dataclass
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class SDMStatusResponse:
    status: str
    port: Optional[str]
    enabled: bool


class SDMService:
    """
    REAL SDM Service - 100% EXACT from original (lines 682-779)
    Calls actual Insight Cloud API for SDM operations
    """
    
    def __init__(self, api_base_url: str, api_key: str, web_url: str):
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.web_url = web_url
        logger.info(f"SDMService initialized for: {api_base_url}")

    def _get_headers(self, user_id: str, account_id: str, token: str, network_id: str = None) -> dict:
        """Get request headers - EXACT from original"""
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
        if network_id:
            headers["networkid"] = network_id
        return headers

    def get_sdm_status_sync(self, user_id: str, account_id: str, token: str, device_id: str, network_id: str) -> SDMStatusResponse:
        """
        Get SDM status for device - REAL endpoint (line 682-715)
        Endpoint: GET device/v1/sdmstatus/{user_id}/{device_id}
        """
        import requests
        import certifi
        
        try:
            logger.info(f"Fetching SDM status for device {device_id}")
            
            # EXACT endpoint from original (line 690)
            endpoint = f"device/v1/sdmstatus/{user_id}/{device_id}"
            url = self.api_base_url + endpoint
            headers = self._get_headers(user_id, account_id, token, network_id)
            
            logger.info(f"GET {url}")
            
            # REAL HTTP call (EXACT FROM ORIGINAL)
            response = requests.get(
                url,
                headers=headers,
                timeout=30,
                verify=certifi.where()
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"SDM status response: {result}")
                
                # Parse response (EXACT FROM ORIGINAL lines 701-706)
                if result.get("response", {}).get("status"):
                    details = result.get("details", {})
                    status = details.get("status", "0")
                    port = details.get("port")
                    enabled = status == "1"
                    
                    logger.info(f"✅ Got SDM status: {status}, port: {port}, enabled: {enabled}")
                    return SDMStatusResponse(status=status, port=port, enabled=enabled)
                else:
                    error_msg = result.get("response", {}).get("message", "Unknown error")
                    logger.error(f"API error: {error_msg}")
                    return SDMStatusResponse(status="0", port=None, enabled=False)
            else:
                try:
                    preview = (response.text or "")[:800]
                except Exception:
                    preview = ""
                logger.error(
                    "SDM status GET failed: HTTP %s for device %s — body: %s",
                    response.status_code,
                    device_id,
                    preview or "(empty)",
                )
                return SDMStatusResponse(status="0", port=None, enabled=False)
                    
        except Exception as e:
            logger.exception(f"Failed to get SDM status: {str(e)}")
            return SDMStatusResponse(status="0", port=None, enabled=False)

    def set_sdm_status_sync(self, user_id: str, account_id: str, token: str, device_id: str, network_id: str, enable: bool) -> bool:
        """
        Enable/Disable SDM for device - REAL endpoint (line 718-743)
        Endpoint: POST device/v1/sdmstatus/{user_id}/{device_id}
        """
        import requests
        import certifi
        
        try:
            logger.info(f"{'Enabling' if enable else 'Disabling'} SDM for device {device_id}")
            
            # EXACT endpoint from original (line 723)
            endpoint = f"device/v1/sdmstatus/{user_id}/{device_id}"
            url = self.api_base_url + endpoint
            headers = self._get_headers(user_id, account_id, token, network_id)
            
            # EXACT payload from original (line 724)
            sdm_data = {"status": "1" if enable else "0"}
            
            logger.info(f"POST {url}")
            logger.info(f"Payload: {sdm_data}")
            
            # REAL HTTP call (EXACT FROM ORIGINAL)
            response = requests.post(
                url,
                json=sdm_data,
                headers=headers,
                timeout=30,
                verify=certifi.where()
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"SDM set response: {result}")
                
                # Parse response (EXACT FROM ORIGINAL lines 733-739)
                if result.get("response", {}).get("status"):
                    logger.info(f"✅ Successfully {'enabled' if enable else 'disabled'} SDM")
                    return True
                else:
                    error_msg = result.get("response", {}).get("message", "Unknown error")
                    logger.error(f"API error: {error_msg}")
                    return False
            else:
                logger.error(f"API returned status {response.status_code}")
                return False
                
        except Exception as e:
            logger.exception(f"Failed to {'enable' if enable else 'disable'} SDM: {str(e)}")
            return False

    def share_diagnostics_sync(self, user_id: str, account_id: str, token: str, device_id: str, network_id: str, email_list: List[str]) -> bool:
        """
        Share device diagnostics - REAL endpoint (line 745-779)
        Endpoint: POST device/v2/diagnostic/{device_id}/{user_id}
        """
        import requests
        import certifi
        
        try:
            logger.info(f"Sharing diagnostics for device {device_id} with emails: {email_list}")
            
            # EXACT endpoint from original (line 750)
            endpoint = f"device/v2/diagnostic/{device_id}/{user_id}"
            url = self.api_base_url + endpoint
            headers = self._get_headers(user_id, account_id, token, network_id)
            
            # EXACT payload structure from original (lines 753-757)
            diagnostic_data = {
                "diagnosticInfo": [
                    {"email": email.strip()} for email in email_list
                ]
            }
            
            logger.info(f"POST {url}")
            logger.info(f"Payload: {diagnostic_data}")
            
            # REAL HTTP call (EXACT FROM ORIGINAL)
            response = requests.post(
                url,
                json=diagnostic_data,
                headers=headers,
                timeout=30,
                verify=certifi.where()
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Diagnostics share response: {result}")
                
                # Parse response (EXACT FROM ORIGINAL lines 769-775)
                if result.get("response", {}).get("status"):
                    logger.info(f"✅ Successfully shared diagnostics")
                    return True
                else:
                    error_msg = result.get("response", {}).get("message", "Unknown error")
                    logger.error(f"API error: {error_msg}")
                    return False
            else:
                logger.error(f"API returned status {response.status_code}")
                return False
                
        except Exception as e:
            logger.exception(f"Failed to share diagnostics: {str(e)}")
            return False
