"""
Real Authentication Service - Extracted from original sdm_manager_gui.py
This is 100% exact logic from the original, no dummy data
"""

import requests
import logging
from typing import Optional
from dataclasses import dataclass

from services.api_service import APIService

logger = logging.getLogger(__name__)


@dataclass
class AuthResponse:
    """Response from authentication"""
    success: bool
    user_id: str
    token: str
    email: str
    account_id: str


class Config:
    """Configuration wrapper"""
    def __init__(self, environment: str = "pri-qa"):
        self.ENVIRONMENTS = {
            "pri-qa": {
                "name": "Primary QA Environment",
                "api_base_url": "https://pri-qa-api-web.insight.netgear.com/insightappcom/",
                "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
                "web_url": "https://pri-qa.insight.netgear.com",
            },
            "demo-aux": {
                "name": "Demo Aux Environment",
                "api_base_url": "https://demo-aux-api-web.insight.netgear.com/insightappcom/",
                "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
                "web_url": "https://demo-aux.insight.netgear.com"
            },
            "maint-qa": {
                "name": "Maintenance QA Environment",
                "api_base_url": "https://maint-qa-api-web.insight.netgear.com/insightappcom/",
                "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
                "web_url": "https://maint-qa.insight.netgear.com",
            },
            "production": {
                "name": "Production Environment",
                "api_base_url": "https://api-web.insight.netgear.com/insightappcom/",
                "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
                "web_url": "https://insight.netgear.com",
            },
            "beta": {
                "name": "Beta Environment",
                "api_base_url": "https://beta-api-web.insight.netgear.com/insightappcom/",
                "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
                "web_url": "https://beta.insight.netgear.com"
            },
            "demo": {
                "name": "Demo Environment",
                "api_base_url": "https://demo-api-web.insight.netgear.com/insightappcom/",
                "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
                "web_url": "https://demo.insight.netgear.com"
            },
            "maint-beta": {
                "name": "Maintenance Beta Environment", 
                "api_base_url": "https://maint-beta-api-web.insight.netgear.com/insightappcom/",
                "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
                "web_url": "https://maint-beta.insight.netgear.com"
            },
            "maint-dev": {
                "name": "Maintenance Dev Environment",
                "api_base_url": "https://maint-dev-api-web.insight.netgear.com/insightappcom/",
                "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
                "web_url": "https://maint-dev.insight.netgear.com"
            },
            "pri-dev": {
                "name": "Primary Dev Environment",
                "api_base_url": "https://pri-dev-api-web.insight.netgear.com/insightappcom/",
                "api_key": "pP3dO6k6lf2N83UEWUjH480VUXhtqCNqa0g8ONeM",
                "web_url": "https://pri-dev.insight.netgear.com"
            }
        }
        
        self.REQUEST_TIMEOUT = 30
        self.SSL_VERIFY = True
        
        if environment not in self.ENVIRONMENTS:
            environment = "pri-qa"
        
        env_config = self.ENVIRONMENTS[environment]
        self.current_environment = environment
        self.API_BASE_URL = env_config["api_base_url"]
        self.API_KEY = env_config["api_key"]
        self.WEB_URL = env_config["web_url"]
        self.ENVIRONMENT_NAME = env_config["name"]


def get_requests_verify_config(config: Config) -> str:
    """Get SSL verification config for requests library"""
    try:
        import certifi
        return certifi.where()
    except:
        return True


class AuthService:
    """
    EXACT REPLICA of original AuthService from sdm_manager_gui.py (lines 276-420)
    100% REAL authentication logic - no dummy data
    """
    
    def __init__(self, config=None):
        self.config = config or Config()
        logger.info(f"AuthService initialized for environment: {self.config.ENVIRONMENT_NAME}")

    def authenticate_user(self, email: str, password: str) -> Optional[AuthResponse]:
        """
        Authenticate user with Swagger API (REAL LOGIC)
        
        Source: Original lines 280-299
        """
        try:
            logger.info(f"Starting email/password authentication for: {email}")
            
            # Use the backend Swagger authenticate endpoint
            logger.info("Attempting Swagger authenticate endpoint...")
            auth_result = self._try_swagger_authenticate(email, password)
            if auth_result and auth_result.success:
                logger.info("SUCCESS: Direct email/password authentication succeeded!")
                return auth_result
            else:
                logger.error("Direct authentication failed")
                logger.info("TIP: Try Manual Credentials if email/password doesn't work")
            
            return None
                
        except Exception as e:
            logger.exception(f"Authentication error: {str(e)}")
            return None

    def authenticate_manual_session(
        self,
        user_id: str,
        account_id: str,
        token: str,
        display_email: Optional[str] = None,
    ) -> Optional[AuthResponse]:
        """
        Manual login: validate _Id, accountId, accessToken from browser cookies against Insight.
        Mirrors sdm_manager_gui manual dialog (no Cognito swagger call — session is already established).
        """
        uid = (user_id or "").strip()
        aid = (account_id or "").strip()
        raw_tok = (token or "").strip()
        if not all([uid, aid, raw_tok]):
            logger.error("Manual auth: missing user_id, account_id, or token")
            return None

        clean_token = raw_tok
        if "accessToken=" in clean_token:
            clean_token = clean_token.split("accessToken=")[1].split(";")[0]
        clean_token = clean_token.strip()

        api = APIService(self.config.API_BASE_URL, self.config.API_KEY, self.config.WEB_URL)
        ok, err = api.verify_session_credentials_sync(uid, aid, clean_token)
        if not ok:
            logger.error("Manual auth failed: %s", err)
            return None

        email_out = (display_email or "").strip()
        if not email_out:
            resolved = api.get_user_profile_email_sync(uid, aid, clean_token)
            if resolved:
                email_out = resolved
            else:
                email_out = f"{uid}@insight.session"

        return AuthResponse(
            success=True,
            user_id=uid,
            token=clean_token,
            email=email_out,
            account_id=aid,
        )

    def _try_swagger_authenticate(self, email: str, password: str) -> Optional[AuthResponse]:
        """
        Try direct Swagger authenticate endpoint
        
        Source: Original lines 301-415
        EXACT REPLICATION - 100% REAL LOGIC
        """
        try:
            logger.info(f"Using backend Swagger authentication API for: {email}")
            
            # Simple payload - backend only needs email and password (EXACT FROM ORIGINAL)
            auth_data = {
                "email": email,
                "password": password
            }
            
            # Minimal headers - backend doesn't require complex browser headers (EXACT FROM ORIGINAL)
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            # Call the Spring Boot SwaggerAuthController endpoint (EXACT FROM ORIGINAL)
            endpoint = f"{self.config.API_BASE_URL}public/v1/swagger/authenticate"
            logger.info(f"POST {endpoint}")
            
            response = requests.post(
                endpoint,
                json=auth_data,
                headers=headers,
                timeout=self.config.REQUEST_TIMEOUT,
                verify=get_requests_verify_config(self.config)
            )
            
            logger.info(f"Swagger authenticate status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Swagger authenticate response: {result}")
                
                # Check if MFA is required first (EXACT FROM ORIGINAL)
                if result.get("mfaRequired"):
                    logger.warning("MFA/2FA is required for this account")
                    challenge_name = result.get("challengeName", "")
                    session = result.get("session", "")
                    logger.info(f"Challenge: {challenge_name}")
                    
                    # For now, we'll return None for MFA cases (EXACT FROM ORIGINAL)
                    logger.error("MFA handling not yet implemented in Python backend")
                    logger.info("TIP: Use Manual Credentials if you have browser session with MFA already completed")
                    return None
                
                # Check for successful authentication (EXACT FROM ORIGINAL)
                elif result.get("success"):
                    logger.info("SUCCESS: Direct authentication successful!")
                    
                    # Extract data from backend response format (EXACT FROM ORIGINAL)
                    token = result.get("token", "")  # Backend access token
                    account_id = result.get("accountId", "")
                    user_id = result.get("userId", result.get("_id", ""))
                    email_resp = result.get("email", email)
                    
                    logger.info(f"User ID: {user_id}")
                    logger.info(f"Account ID: {account_id}")
                    logger.info(f"Email: {email_resp}")
                    
                    # Create AuthResponse matching expected format (EXACT FROM ORIGINAL)
                    return AuthResponse(
                        success=True,
                        user_id=user_id,
                        token=token,
                        email=email_resp,
                        account_id=account_id
                    )
                
                else:
                    # Authentication failed (EXACT FROM ORIGINAL)
                    error_msg = result.get("error", "Authentication failed")
                    error_type = result.get("errorType", "")
                    logger.error(f"Authentication failed: {error_msg}")
                    if error_type:
                        logger.error(f"Error type: {error_type}")
                    return None
                    
            elif response.status_code == 400:
                logger.error("Bad request - check email and password format")
                return None
                
            elif response.status_code == 401:
                # Invalid credentials (EXACT FROM ORIGINAL)
                try:
                    result = response.json()
                except:
                    result = {}
                error_msg = result.get("error", "Invalid credentials")
                error_type = result.get("errorType", "")
                logger.error(f"Authentication failed: {error_msg}")
                if error_type:
                    logger.error(f"Error type: {error_type}")
                logger.info("TIP: Double-check your email and password are correct for this environment")
                return None
                
            elif response.status_code == 500:
                logger.error("Server error - Authentication service may be unreachable")
                return None
                
            else:
                logger.error(f"Unexpected response: {response.status_code}")
                return None
                    
        except Exception as e:
            error_msg = str(e)
            logger.exception(f"Swagger authenticate exception: {error_msg}")
            
            # Provide helpful SSL error guidance (EXACT FROM ORIGINAL)
            if "SSL" in error_msg or "certificate" in error_msg.lower():
                logger.error("SSL Certificate Error Detected!")
                logger.info("This is common on macOS. The SSL configuration has been updated to help resolve this.")
                logger.info("If this persists, you can:")
                logger.info("1. Try: pip install --upgrade certifi")
                logger.info("2. Use Manual Credentials authentication instead")
                
            return None
