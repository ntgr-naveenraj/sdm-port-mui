"""
SDM Manager Backend - Flask Application with REAL Logic

100% implementation from original sdm_manager_gui.py
No dummy data - real API calls only
"""

from flask import Flask, request
from flask_cors import CORS
import logging
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from services.auth_service import AuthService, Config, AuthResponse
from services.api_service import APIService
from services.batch_ssh import BatchSSHService, DeviceConfig
from services.csv_parser import CSVParser
from services.sdm_service import SDMService
from services.file_transfer_sshcommand import (
    FtReliability,
    get_ft_manager,
    load_sshcommand_module,
    sshcommand_available,
)

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.route('/')
def root():
    return {
        "name": "SDM Manager API",
        "version": "1.0.0",
        "status": "running",
        "mode": "REAL LOGIC - 100% from original"
    }

@app.route('/health')
def health():
    return {
        "status": "healthy",
        "environment": "pri-qa",
        "mode": "REAL"
    }

# REAL AUTHENTICATION ENDPOINT
@app.route('/api/v1/auth/login', methods=['POST'])
def login():
    """
    REAL authentication endpoint using extracted AuthService
    100% logic from original sdm_manager_gui.py
    """
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        environment = data.get('environment', 'pri-qa')
        
        if not email or not password:
            return {
                "success": False,
                "error": "Email and password are required"
            }, 400
        
        # Use REAL AuthService with REAL endpoint
        auth_service = AuthService(Config(environment))
        result = auth_service.authenticate_user(email, password)
        
        if result:
            return {
                "success": True,
                "user_id": result.user_id,
                "token": result.token,
                "email": result.email,
                "account_id": result.account_id,
                "environment": environment
            }, 200
        else:
            return {
                "success": False,
                "error": "Authentication failed - please check credentials"
            }, 401
            
    except Exception as e:
        logger.exception(f"Login error: {str(e)}")
        return {
            "success": False,
            "error": f"Server error: {str(e)}"
        }, 500

@app.route('/api/v1/auth/manual', methods=['POST'])
def login_manual():
    """
    Manual credentials: User ID (_Id), Account ID, Access Token from browser cookies.
    Validates session with Insight organization/v1/orgInfo (same as post-Swagger API usage).
    """
    try:
        data = request.get_json() or {}
        user_id = data.get("user_id")
        account_id = data.get("account_id")
        token = data.get("token")
        environment = data.get("environment", "pri-qa")
        display_email = data.get("email")

        if not user_id or not account_id or not token:
            return {
                "success": False,
                "error": "user_id, account_id, and token are required",
            }, 400

        auth_service = AuthService(Config(environment))
        result = auth_service.authenticate_manual_session(
            str(user_id).strip(),
            str(account_id).strip(),
            str(token).strip(),
            display_email=str(display_email).strip() if display_email else None,
        )

        if result:
            return {
                "success": True,
                "user_id": result.user_id,
                "token": result.token,
                "email": result.email,
                "account_id": result.account_id,
                "environment": environment,
            }, 200

        return {
            "success": False,
            "error": "Invalid session — Insight rejected these credentials for this environment. "
            "Copy fresh _Id, accountId, and accessToken from the same Insight tab you are logged into.",
        }, 401

    except Exception as e:
        logger.exception(f"Manual login error: {str(e)}")
        return {
            "success": False,
            "error": f"Server error: {str(e)}",
        }, 500


@app.route('/api/v1/auth/environments', methods=['GET'])
def get_environments():
    """Get list of available environments - REAL from config"""
    config = Config()
    environments = []
    for env_key, env_config in config.ENVIRONMENTS.items():
        environments.append({
            "id": env_key,
            "name": env_config["name"]
        })
    
    return {
        "success": True,
        "environments": environments,
        "default": "pri-qa"
    }, 200

# REAL API ENDPOINTS
@app.route('/api/v1/orgs/', methods=['GET'])
def get_organizations():
    """REAL organizations endpoint - calls actual Insight Cloud API"""
    try:
        user_id = request.headers.get('user-id')
        account_id = request.headers.get('account-id')
        token = request.headers.get('token')
        environment = request.headers.get('environment', 'pri-qa')
        
        if not all([user_id, account_id, token]):
            return {"success": False, "error": "Missing auth headers"}, 401
        
        # Use REAL API Service
        config = Config(environment)
        real_api = APIService(config.API_BASE_URL, config.API_KEY, config.WEB_URL)
        
        orgs = real_api.get_organizations_sync(user_id, account_id, token)
        
        return {
            "success": True,
            "items": [{"org_id": o.org_id, "org_name": o.org_name, "location_count": o.location_count, "device_count": o.device_count} for o in orgs],
            "total": len(orgs)
        }, 200
    except Exception as e:
        logger.exception(f"Get organizations error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/v1/devices/locations/<org_id>', methods=['GET'])
def get_locations(org_id):
    """REAL locations endpoint - calls actual Insight Cloud API"""
    try:
        user_id = request.headers.get('user-id')
        account_id = request.headers.get('account-id')
        token = request.headers.get('token')
        environment = request.headers.get('environment', 'pri-qa')
        
        if not all([user_id, account_id, token]):
            return {"success": False, "error": "Missing auth headers"}, 401
        
        # Use REAL API Service
        config = Config(environment)
        real_api = APIService(config.API_BASE_URL, config.API_KEY, config.WEB_URL)
        
        locations = real_api.get_locations_sync(user_id, account_id, token, org_id)
        
        return {
            "success": True,
            "items": [{"network_id": l.network_id, "network_name": l.network_name, "device_count": l.device_count, "ap_count": l.ap_count} for l in locations],
            "total": len(locations)
        }, 200
    except Exception as e:
        logger.exception(f"Get locations error: {str(e)}")
        return {"success": False, "error": str(e)}, 500


def _serialize_ap_devices_with_sdm(devices, user_id, account_id, token, environment):
    """Build JSON list with parallel SDM status (Insight AP devices already filtered)."""
    config = Config(environment)
    sdm_by_id = {}
    if devices:
        sdm_service = SDMService(config.API_BASE_URL, config.API_KEY, config.WEB_URL)

        def _fetch_sdm(ap):
            try:
                r = sdm_service.get_sdm_status_sync(
                    user_id, account_id, token, ap.device_id, ap.network_id
                )
                port_raw = r.port
                if port_raw is None or port_raw == "":
                    port_out = None
                else:
                    port_out = str(port_raw)
                return (ap.device_id, ap.network_id), r.status, port_out
            except Exception:
                logger.exception("SDM status fetch failed for device %s", ap.device_id)
                return (ap.device_id, ap.network_id), "0", None

        max_workers = min(24, max(4, len(devices)))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [pool.submit(_fetch_sdm, d) for d in devices]
            for fut in as_completed(futures):
                key, st, pt = fut.result()
                sdm_by_id[key] = (st, pt)

    def _item_dict(d):
        st, pt = sdm_by_id.get((d.device_id, d.network_id), ("0", None))
        item = {
            "device_id": d.device_id,
            "serial_no": d.serial_no,
            "name": d.name,
            "model": d.model,
            "ip_address": d.ip_address,
            "mac_address": d.mac_address,
            "network_id": d.network_id,
            "network_name": d.network_name,
            "device_status": d.device_status,
            "last_seen": d.last_seen,
            "sdm_status": st,
            "sdm_port": pt,
        }
        if d.org_id:
            item["org_id"] = d.org_id
        if d.org_name:
            item["organization"] = d.org_name
        return item

    return {
        "success": True,
        "items": [_item_dict(d) for d in devices],
        "total": len(devices),
    }


@app.route('/api/v1/ap-devices/all-orgs', methods=['GET'])
def get_ap_devices_all_orgs():
    """All AP devices across all organizations (parallel per-org network fan-out)."""
    try:
        user_id = request.headers.get('user-id')
        account_id = request.headers.get('account-id')
        token = request.headers.get('token')
        environment = request.headers.get('environment', 'pri-qa')

        if not all([user_id, account_id, token]):
            return {"success": False, "error": "Missing auth headers"}, 401

        config = Config(environment)
        real_api = APIService(config.API_BASE_URL, config.API_KEY, config.WEB_URL)
        devices = real_api.get_ap_devices_all_orgs_sync(user_id, account_id, token)
        return _serialize_ap_devices_with_sdm(devices, user_id, account_id, token, environment), 200
    except Exception as e:
        logger.exception(f"Get all-orgs AP devices error: {str(e)}")
        return {"success": False, "error": str(e)}, 500


@app.route('/api/v1/orgs/<org_id>/ap-devices', methods=['GET'])
def get_ap_devices_for_org(org_id):
    """All AP devices for one organization (all networks under org)."""
    try:
        user_id = request.headers.get('user-id')
        account_id = request.headers.get('account-id')
        token = request.headers.get('token')
        environment = request.headers.get('environment', 'pri-qa')

        if not all([user_id, account_id, token]):
            return {"success": False, "error": "Missing auth headers"}, 401

        config = Config(environment)
        real_api = APIService(config.API_BASE_URL, config.API_KEY, config.WEB_URL)
        org_name = None
        try:
            for o in real_api.get_organizations_sync(user_id, account_id, token):
                if o.org_id == org_id:
                    org_name = o.org_name
                    break
        except Exception:
            logger.exception("Could not resolve org name for %s", org_id)

        devices = real_api.get_ap_devices_for_org_sync(
            user_id, account_id, token, org_id, org_name
        )
        return _serialize_ap_devices_with_sdm(devices, user_id, account_id, token, environment), 200
    except Exception as e:
        logger.exception(f"Get org AP devices error: {str(e)}")
        return {"success": False, "error": str(e)}, 500


@app.route('/api/v1/devices/<network_id>', methods=['GET'])
def get_devices(network_id):
    """REAL devices endpoint - calls actual Insight Cloud API (AP devices only for network)."""
    try:
        user_id = request.headers.get('user-id')
        account_id = request.headers.get('account-id')
        token = request.headers.get('token')
        environment = request.headers.get('environment', 'pri-qa')

        if not all([user_id, account_id, token]):
            return {"success": False, "error": "Missing auth headers"}, 401

        config = Config(environment)
        real_api = APIService(config.API_BASE_URL, config.API_KEY, config.WEB_URL)

        devices = real_api.get_ap_devices_sync(user_id, account_id, token, network_id)
        return _serialize_ap_devices_with_sdm(devices, user_id, account_id, token, environment), 200
    except Exception as e:
        logger.exception(f"Get devices error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

# SDM OPERATIONS ENDPOINTS (REAL LOGIC)
@app.route('/api/v1/sdm/status/<device_id>/<network_id>', methods=['GET'])
def get_sdm_status(device_id, network_id):
    """Get SDM status for device - calls actual Insight Cloud API"""
    try:
        user_id = request.headers.get('user-id')
        account_id = request.headers.get('account-id')
        token = request.headers.get('token')
        environment = request.headers.get('environment', 'pri-qa')
        
        if not all([user_id, account_id, token]):
            return {"success": False, "error": "Missing auth headers"}, 401
        
        from services.sdm_service import SDMService
        config = Config(environment)
        sdm_service = SDMService(config.API_BASE_URL, config.API_KEY, config.WEB_URL)
        
        status = sdm_service.get_sdm_status_sync(user_id, account_id, token, device_id, network_id)
        
        return {
            "success": True,
            "status": status.status,
            "port": status.port,
            "enabled": status.enabled
        }, 200
    except Exception as e:
        logger.exception(f"Get SDM status error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/v1/sdm/enable', methods=['POST'])
def enable_sdm():
    """Enable SDM for device - calls actual Insight Cloud API"""
    try:
        data = request.get_json()
        user_id = request.headers.get('user-id')
        account_id = request.headers.get('account-id')
        token = request.headers.get('token')
        environment = request.headers.get('environment', 'pri-qa')
        device_id = data.get('device_id')
        network_id = data.get('network_id')
        
        if not all([user_id, account_id, token, device_id, network_id]):
            return {"success": False, "error": "Missing required parameters"}, 400
        
        from services.sdm_service import SDMService
        config = Config(environment)
        sdm_service = SDMService(config.API_BASE_URL, config.API_KEY, config.WEB_URL)
        
        success = sdm_service.set_sdm_status_sync(user_id, account_id, token, device_id, network_id, enable=True)
        
        return {
            "success": success,
            "message": "SDM enabled successfully" if success else "Failed to enable SDM"
        }, 200 if success else 500
    except Exception as e:
        logger.exception(f"Enable SDM error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/v1/sdm/disable', methods=['POST'])
def disable_sdm():
    """Disable SDM for device - calls actual Insight Cloud API"""
    try:
        data = request.get_json()
        user_id = request.headers.get('user-id')
        account_id = request.headers.get('account-id')
        token = request.headers.get('token')
        environment = request.headers.get('environment', 'pri-qa')
        device_id = data.get('device_id')
        network_id = data.get('network_id')
        
        if not all([user_id, account_id, token, device_id, network_id]):
            return {"success": False, "error": "Missing required parameters"}, 400
        
        from services.sdm_service import SDMService
        config = Config(environment)
        sdm_service = SDMService(config.API_BASE_URL, config.API_KEY, config.WEB_URL)
        
        success = sdm_service.set_sdm_status_sync(user_id, account_id, token, device_id, network_id, enable=False)
        
        return {
            "success": success,
            "message": "SDM disabled successfully" if success else "Failed to disable SDM"
        }, 200 if success else 500
    except Exception as e:
        logger.exception(f"Disable SDM error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/v1/sdm/diagnostics', methods=['POST'])
def share_diagnostics():
    """Share device diagnostics - calls actual Insight Cloud API"""
    try:
        data = request.get_json()
        user_id = request.headers.get('user-id')
        account_id = request.headers.get('account-id')
        token = request.headers.get('token')
        environment = request.headers.get('environment', 'pri-qa')
        device_id = data.get('device_id')
        network_id = data.get('network_id')
        email_list = data.get('email_list', [])
        
        if not all([user_id, account_id, token, device_id, network_id, email_list]):
            return {"success": False, "error": "Missing required parameters"}, 400
        
        from services.sdm_service import SDMService
        config = Config(environment)
        sdm_service = SDMService(config.API_BASE_URL, config.API_KEY, config.WEB_URL)
        
        success = sdm_service.share_diagnostics_sync(user_id, account_id, token, device_id, network_id, email_list)
        
        return {
            "success": success,
            "message": "Diagnostics shared successfully" if success else "Failed to share diagnostics"
        }, 200 if success else 500
    except Exception as e:
        logger.exception(f"Share diagnostics error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

# SSH OPERATIONS ENDPOINTS (REAL LOGIC)
@app.route('/api/v1/ssh/execute', methods=['POST'])
def execute_ssh_command():
    """Execute SSH command on device - calls actual device via SSH"""
    try:
        data = request.get_json()
        device_serial = data.get('device_serial')
        ip_address = data.get('ip_address')
        sdm_port = data.get('sdm_port')
        command = data.get('command')
        timeout = data.get('timeout', 30)
        
        if not all([device_serial, ip_address, sdm_port, command]):
            return {"success": False, "error": "Missing required parameters"}, 400
        
        from services.ssh_service import SSHService
        ssh_service = SSHService()
        
        result = ssh_service.execute_command_sync(
            device_serial, ip_address, int(sdm_port), command, timeout
        )
        
        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "exit_code": result.exit_code
        }, 200 if result.success else 500
    except Exception as e:
        logger.exception(f"Execute SSH error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/v1/ssh/upload', methods=['POST'])
def upload_file():
    """Upload file to device via SCP - real file transfer"""
    try:
        data = request.get_json()
        device_serial = data.get('device_serial')
        ip_address = data.get('ip_address')
        sdm_port = data.get('sdm_port')
        local_path = data.get('local_path')
        remote_path = data.get('remote_path')
        timeout = data.get('timeout', 60)
        
        if not all([device_serial, ip_address, sdm_port, local_path, remote_path]):
            return {"success": False, "error": "Missing required parameters"}, 400
        
        from services.ssh_service import SSHService
        ssh_service = SSHService()
        
        result = ssh_service.upload_file_sync(
            device_serial, ip_address, int(sdm_port), local_path, remote_path, timeout
        )
        
        return {
            "success": result.success,
            "message": result.message,
            "bytes_transferred": result.bytes_transferred,
            "md5sum": result.md5sum
        }, 200 if result.success else 500
    except Exception as e:
        logger.exception(f"Upload file error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/v1/ssh/download', methods=['POST'])
def download_file():
    """Download file from device via SCP - real file transfer"""
    try:
        data = request.get_json()
        device_serial = data.get('device_serial')
        ip_address = data.get('ip_address')
        sdm_port = data.get('sdm_port')
        remote_path = data.get('remote_path')
        local_path = data.get('local_path')
        timeout = data.get('timeout', 60)
        
        if not all([device_serial, ip_address, sdm_port, remote_path, local_path]):
            return {"success": False, "error": "Missing required parameters"}, 400
        
        from services.ssh_service import SSHService
        ssh_service = SSHService()
        
        result = ssh_service.download_file_sync(
            device_serial, ip_address, int(sdm_port), remote_path, local_path, timeout
        )
        
        return {
            "success": result.success,
            "message": result.message,
            "bytes_transferred": result.bytes_transferred,
            "md5sum": result.md5sum
        }, 200 if result.success else 500
    except Exception as e:
        logger.exception(f"Download file error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/v1/ssh/batch', methods=['POST'])
def execute_batch_commands():
    """Execute multiple commands on device"""
    try:
        data = request.get_json()
        device_serial = data.get('device_serial')
        ip_address = data.get('ip_address')
        sdm_port = data.get('sdm_port')
        commands = data.get('commands', [])
        timeout = data.get('timeout', 60)
        
        if not all([device_serial, ip_address, sdm_port, commands]):
            return {"success": False, "error": "Missing required parameters"}, 400
        
        from services.ssh_service import SSHService
        ssh_service = SSHService()
        
        result = ssh_service.execute_batch_commands_sync(
            device_serial, ip_address, int(sdm_port), commands, timeout
        )
        
        return {
            "success": result.success,
            "output": result.output,
            "error": result.error,
            "exit_code": result.exit_code
        }, 200 if result.success else 500
    except Exception as e:
        logger.exception(f"Batch SSH error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

# BATCH OPERATIONS ENDPOINTS (REAL LOGIC)
@app.route('/api/v1/batch/parse-csv', methods=['POST'])
def parse_csv():
    """Parse CSV file and return device list"""
    try:
        if 'file' not in request.files:
            return {"success": False, "error": "No file provided"}, 400
        
        file = request.files['file']
        if file.filename == '':
            return {"success": False, "error": "No file selected"}, 400
        
        # Save temp file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.csv') as tmp:
            file.save(tmp.name)
            temp_path = Path(tmp.name)
        
        try:
            # Parse CSV (REAL LOGIC)
            devices, errors = CSVParser.parse_csv(temp_path)
            
            # Validate devices (REAL LOGIC)
            valid_devices, validation_errors = CSVParser.validate_devices(devices)
            
            all_errors = errors + validation_errors
            
            return {
                "success": len(valid_devices) > 0,
                "devices": CSVParser.devices_to_dict(valid_devices),
                "errors": all_errors,
                "total": len(valid_devices),
                "error_count": len(all_errors)
            }, 200
        finally:
            temp_path.unlink()
            
    except Exception as e:
        logger.exception(f"Parse CSV error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/v1/batch/execute', methods=['POST'])
def batch_execute():
    """Execute commands on multiple devices (REAL LOGIC)"""
    try:
        data = request.get_json() or {}
        devices_data = data.get('devices', [])
        command = data.get('command', '')
        jump_host = data.get('jump_host', 'user@smbshells.netgear.com')
        jump_port = data.get('jump_port', 443)
        ssh_key_path = data.get('ssh_key_path', '')
        
        if not devices_data or not command:
            return {"success": False, "error": "Missing devices or command"}, 400
        
        # Convert to DeviceConfig objects
        devices = [
            DeviceConfig(
                name=d.get('name'),
                ip_address=d.get('ip_address'),
                sdm_port=int(d.get('sdm_port', 22)),
                serial_no=d.get('serial_no'),
                model=d.get('model')
            )
            for d in devices_data
        ]
        
        # Sequential AP processing + pause between APs (legacy Tk / sdm_manager_gui style)
        rel = _parse_ft_reliability(data)
        batch_service = BatchSSHService(jump_host, int(jump_port), Path(ssh_key_path))
        results = batch_service.execute_batch(
            devices,
            command,
            pause_between_aps_sec=rel.pause_between_batch_aps_sec,
        )
        
        succeeded = len([r for r in results if r.get('success')])
        
        return {
            "success": True,
            "results": results,
            "summary": {
                "total": len(results),
                "succeeded": succeeded,
                "failed": len(results) - succeeded,
            },
        }, 200

    except Exception as e:
        logger.exception(f"Batch execute error: {str(e)}")
        return {"success": False, "error": str(e)}, 500


def _parse_ft_reliability(data: dict) -> FtReliability:
    r = data.get("reliability") or {}
    try:
        er = int(r.get("extra_connect_retries", 2))
    except (TypeError, ValueError):
        er = 2
    try:
        bb = float(r.get("backoff_base_sec", 0.5))
    except (TypeError, ValueError):
        bb = 0.5
    try:
        pac = float(r.get("pause_after_connect_sec", 0.2))
    except (TypeError, ValueError):
        pac = 0.2
    try:
        pba = float(r.get("pause_between_batch_aps_sec", 0.15))
    except (TypeError, ValueError):
        pba = 0.15
    return FtReliability(
        extra_connect_retries=max(0, min(8, er)),
        backoff_base_sec=max(0.05, min(10.0, bb)),
        pause_after_connect_sec=max(0.0, min(5.0, pac)),
        pause_between_batch_aps_sec=max(0.0, min(5.0, pba)),
        ping_shell_after_connect=bool(r.get("ping_shell_after_connect", False)),
        reconnect_if_session_dead=bool(r.get("reconnect_if_session_dead", False)),
    )


@app.route("/api/v1/ft/capabilities", methods=["GET"])
def ft_capabilities():
    ok, err = sshcommand_available()
    return {"sshcommand_available": ok, "sshcommand_error": err or None}, 200


@app.route("/api/v1/ft/connect", methods=["POST"])
def ft_connect():
    try:
        data = request.get_json() or {}
        devices_data = data.get("devices", [])
        jump_host = data.get("jump_host", "user@smbshells.netgear.com")
        jump_port = int(data.get("jump_port", 443))
        ssh_key_path = data.get("ssh_key_path", "")
        if not devices_data:
            return {"success": False, "error": "No devices"}, 400
        if not ssh_key_path or not Path(ssh_key_path).expanduser().is_file():
            return {"success": False, "error": "Invalid ssh_key_path"}, 400
        rel = _parse_ft_reliability(data)
        log_lines: list = []
        mgr = get_ft_manager()
        mgr.connect_cancel.clear()
        results = mgr.connect_devices(
            devices_data,
            jump_host,
            jump_port,
            Path(ssh_key_path).expanduser(),
            rel,
            log_lines=log_lines,
        )
        ok_n = sum(1 for r in results if r.get("success"))
        return {
            "success": True,
            "results": results,
            "log_lines": log_lines,
            "summary": {"total": len(results), "succeeded": ok_n, "failed": len(results) - ok_n},
        }, 200
    except Exception as e:
        logger.exception("ft_connect")
        return {"success": False, "error": str(e)}, 500


@app.route("/api/v1/ft/disconnect", methods=["POST"])
def ft_disconnect():
    try:
        mgr = get_ft_manager()
        mod = load_sshcommand_module()
        mgr.disconnect_all(mod)
        return {"success": True}, 200
    except Exception as e:
        logger.exception("ft_disconnect")
        return {"success": False, "error": str(e)}, 500


@app.route("/api/v1/ft/transfer/stop", methods=["POST"])
def ft_transfer_stop():
    get_ft_manager().transfer_cancel.set()
    return {"success": True}, 200


@app.route("/api/v1/ft/sessions", methods=["GET"])
def ft_sessions():
    mgr = get_ft_manager()
    ok, err = sshcommand_available()
    return {
        "sshcommand_available": ok,
        "sshcommand_error": err or None,
        "sessions": mgr.status_snapshot(),
    }, 200


@app.route("/api/v1/ft/explorer/local-list", methods=["POST"])
def ft_explorer_local_list():
    try:
        data = request.get_json() or {}
        path = (data.get("path") or ".").strip()
        ok, err, lines = get_ft_manager().local_list_dir(path)
        return {"success": ok, "error": err or None, "entries": lines}, 200 if ok else 400
    except Exception as e:
        return {"success": False, "error": str(e)}, 500


@app.route("/api/v1/ft/explorer/remote-list", methods=["POST"])
def ft_explorer_remote_list():
    try:
        data = request.get_json() or {}
        ip = (data.get("ip_address") or "").strip()
        try:
            port = int(data.get("sdm_port"))
        except (TypeError, ValueError):
            return {"success": False, "error": "sdm_port required"}, 400
        rpath = (data.get("path") or "/").strip()
        jump_host = data.get("jump_host", "user@smbshells.netgear.com")
        jump_port = int(data.get("jump_port", 443))
        ssh_key_path = data.get("ssh_key_path", "")
        if not ssh_key_path or not Path(ssh_key_path).expanduser().is_file():
            return {"success": False, "error": "Invalid ssh_key_path"}, 400
        rel = _parse_ft_reliability(data)
        ok, err, lines = get_ft_manager().remote_list(
            ip,
            port,
            rpath,
            jump_host,
            jump_port,
            Path(ssh_key_path).expanduser(),
            rel,
        )
        return {"success": ok, "error": err or None, "entries": lines}, 200 if ok else 400
    except Exception as e:
        logger.exception("ft_explorer_remote_list")
        return {"success": False, "error": str(e)}, 500


@app.route('/api/v1/batch/transfer', methods=['POST'])
def batch_transfer():
    """
    Batch file transfer — jump shell only (vendored pexpect + base64), same idea as legacy Tk ``sshcommand``:
    - upload: ``upload_local_paths`` (list of paths on the API host) + ``upload_remote_dir`` (directory on each AP).
    - download: ``download_remote_paths`` (list of remote paths) + ``download_local_root`` (folder on API host;
      each AP gets a subfolder by sanitized AP name).

    Uses ``reliability.pause_between_batch_aps_sec`` between devices (legacy Tk style).
    """
    try:
        data = request.get_json() or {}
        devices_data = data.get('devices', [])
        operation = (data.get('operation') or 'upload').strip().lower()
        jump_host = data.get('jump_host', 'user@smbshells.netgear.com')
        jump_port = int(data.get('jump_port', 443))
        ssh_key_path = data.get('ssh_key_path', '')

        if not devices_data:
            return {"success": False, "error": "No devices selected"}, 400
        if not ssh_key_path or not Path(ssh_key_path).expanduser().is_file():
            return {"success": False, "error": "Invalid or missing ssh_key_path (must exist on API host)"}, 400

        upload_local_paths = data.get('upload_local_paths') or data.get('local_paths')
        upload_remote_dir = data.get('upload_remote_dir') or data.get('remote_path')
        download_remote_paths = data.get('download_remote_paths')
        download_local_root = data.get('download_local_root')
        chmod_x = bool(data.get('chmod_x_after_upload') or data.get('upload_binary'))
        try:
            dl_to = int(data.get('download_timeout_sec', data.get('download_timeout', 900)))
        except (TypeError, ValueError):
            dl_to = 900
        if dl_to < 30 or dl_to > 86400:
            return {"success": False, "error": "download_timeout_sec must be between 30 and 86400"}, 400

        rel = _parse_ft_reliability(data)

        ok_sc, sc_err = sshcommand_available()
        if not ok_sc:
            return {
                "success": False,
                "error": sc_err or "Jump shell (sshcommand) unavailable — install pexpect and run the API on a supported host",
            }, 503
        mgr = get_ft_manager()
        mgr.transfer_cancel.clear()
        log_lines: list = []
        paths = upload_local_paths if isinstance(upload_local_paths, list) else [upload_local_paths] if upload_local_paths else []
        dest = (upload_remote_dir or '').strip()
        rpaths = download_remote_paths
        if isinstance(rpaths, str):
            rpaths = [ln.strip() for ln in rpaths.splitlines() if ln.strip()]
        root = (download_local_root or '').strip()

        if operation == 'upload':
            if not paths or not dest:
                return {"success": False, "error": "Upload requires upload_local_paths and upload_remote_dir"}, 400
            raw_results = mgr.transfer_batch(
                devices_data,
                'upload',
                jump_host=jump_host,
                jump_port=jump_port,
                key_path=Path(ssh_key_path).expanduser(),
                upload_local_paths=[str(Path(p).expanduser()) for p in paths],
                upload_remote_dir=dest,
                download_timeout_sec=dl_to,
                chmod_x_after_upload=chmod_x,
                rel=rel,
                log_lines=log_lines,
            )
        elif operation == 'download':
            if not isinstance(rpaths, list) or not rpaths or not root:
                return {"success": False, "error": "Download requires download_remote_paths and download_local_root"}, 400
            raw_results = mgr.transfer_batch(
                devices_data,
                'download',
                jump_host=jump_host,
                jump_port=jump_port,
                key_path=Path(ssh_key_path).expanduser(),
                download_remote_paths=[str(p).strip() for p in rpaths if str(p).strip()],
                download_local_root=str(Path(root).expanduser()),
                download_timeout_sec=dl_to,
                rel=rel,
                log_lines=log_lines,
            )
        else:
            return {"success": False, "error": "operation must be upload or download"}, 400

        succeeded = len([r for r in raw_results if r.get('success')])
        return {
            "success": True,
            "engine": "sshcommand",
            "log_lines": log_lines,
            "results": raw_results,
            "summary": {
                "total": len(raw_results),
                "succeeded": succeeded,
                "failed": len(raw_results) - succeeded,
            },
        }, 200

    except Exception as e:
        logger.exception(f"Batch transfer error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/v1/devices/export', methods=['POST'])
def export_devices():
    """Export devices to CSV format"""
    try:
        data = request.get_json()
        devices_data = data.get('devices', [])
        
        if not devices_data:
            return {"success": False, "error": "No devices to export"}, 400
        
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow(["Name", "Serial", "Model", "IP", "Status", "SDM Status", "SDM Port", "MAC Address"])
        
        # Data
        for device in devices_data:
            writer.writerow([
                device.get('name', ''),
                device.get('serial_no', ''),
                device.get('model', ''),
                device.get('ip_address', ''),
                "Online" if device.get('device_status') == 1 else "Offline",
                "Enabled" if device.get('sdm_status') == "1" else "Disabled",
                device.get('sdm_port', ''),
                device.get('mac_address', '')
            ])
        
        return {
            "success": True,
            "csv_data": output.getvalue(),
            "filename": "devices_export.csv"
        }, 200
        
    except Exception as e:
        logger.exception(f"Export devices error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

@app.route('/api/v1/sdm/diagnostics/bulk', methods=['POST'])
def share_diagnostics_bulk():
    """Share diagnostics for multiple devices"""
    try:
        data = request.get_json()
        user_id = request.headers.get('user-id')
        account_id = request.headers.get('account-id')
        token = request.headers.get('token')
        environment = request.headers.get('environment', 'pri-qa')
        devices_data = data.get('devices', [])
        email_list = data.get('email_list', [])
        
        if not all([user_id, account_id, token, devices_data, email_list]):
            return {"success": False, "error": "Missing required parameters"}, 400
        
        from services.sdm_service import SDMService
        config = Config(environment)
        sdm_service = SDMService(config.API_BASE_URL, config.API_KEY, config.WEB_URL)
        
        results = []
        for device in devices_data:
            try:
                success = sdm_service.share_diagnostics_sync(
                    user_id, account_id, token,
                    device.get('device_id'),
                    device.get('network_id'),
                    email_list
                )
                results.append({
                    "device": device.get('name'),
                    "device_id": device.get('device_id'),
                    "success": success
                })
            except Exception as e:
                logger.exception(f"Share diagnostics for {device.get('name')}: {str(e)}")
                results.append({
                    "device": device.get('name'),
                    "device_id": device.get('device_id'),
                    "success": False,
                    "error": str(e)
                })
        
        succeeded = len([r for r in results if r.get('success')])
        
        return {
            "success": True,
            "results": results,
            "summary": {
                "total": len(devices_data),
                "succeeded": succeeded,
                "failed": len(devices_data) - succeeded,
                "recipients": email_list
            }
        }, 200
        
    except Exception as e:
        logger.exception(f"Bulk share diagnostics error: {str(e)}")
        return {"success": False, "error": str(e)}, 500

if __name__ == "__main__":
    logger.info("SDM Manager Backend starting...")
    logger.info("Mode: REAL LOGIC (100% from original)")
    logger.info("Using extracted AuthService with real API calls")
    app.run(host="127.0.0.1", port=8000, debug=False)
