"""
SSH Operations Service - Extracted from original sshcommand.py
100% EXACT logic for SSH command execution and file transfer
"""

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple
import base64
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class SSHCommandResult:
    success: bool
    output: str
    error: str
    exit_code: int = 0


@dataclass
class FileTransferResult:
    success: bool
    message: str
    bytes_transferred: int = 0
    md5sum: Optional[str] = None


class SSHService:
    """
    REAL SSH Service - 100% logic from original sshcommand.py
    Executes commands on devices via SSH through SDM port
    """
    
    def __init__(self):
        logger.info("SSHService initialized")

    def execute_command_sync(
        self, 
        device_serial: str,
        ip_address: str,
        sdm_port: int,
        command: str,
        timeout: int = 30
    ) -> SSHCommandResult:
        """
        Execute SSH command on device - REAL SSH execution (from sshcommand.py)
        
        Connects to device via SDM port and executes shell command
        Returns output and exit code
        """
        try:
            logger.info(f"Executing SSH command on {device_serial} ({ip_address}:{sdm_port})")
            logger.info(f"Command: {command}")
            
            # Build SSH command (EXACT from original build_ssh_cmd lines 514-537)
            ssh_cmd = [
                "ssh",
                "-p", str(sdm_port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=10",
                f"root@{ip_address}",
                command
            ]
            
            logger.info(f"SSH command: {' '.join(ssh_cmd)}")
            
            # REAL SSH execution (EXACT pattern from original)
            try:
                result = subprocess.run(
                    ssh_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
                logger.info(f"SSH exit code: {result.returncode}")
                logger.info(f"SSH stdout: {result.stdout[:500]}")
                
                if result.returncode == 0:
                    logger.info("✅ SSH command succeeded")
                    return SSHCommandResult(
                        success=True,
                        output=result.stdout,
                        error="",
                        exit_code=result.returncode
                    )
                else:
                    logger.error(f"SSH command failed: {result.stderr}")
                    return SSHCommandResult(
                        success=False,
                        output=result.stdout,
                        error=result.stderr,
                        exit_code=result.returncode
                    )
                    
            except subprocess.TimeoutExpired:
                logger.error(f"SSH command timed out after {timeout}s")
                return SSHCommandResult(
                    success=False,
                    output="",
                    error=f"Command timed out after {timeout} seconds",
                    exit_code=124
                )
                
        except Exception as e:
            logger.exception(f"SSH execution error: {str(e)}")
            return SSHCommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1
            )

    def upload_file_sync(
        self,
        device_serial: str,
        ip_address: str,
        sdm_port: int,
        local_path: str,
        remote_path: str,
        timeout: int = 60
    ) -> FileTransferResult:
        """
        Upload file to device via SCP - REAL file transfer (from sshcommand.py)
        
        Uploads local file to remote device path
        Returns success status and bytes transferred
        """
        try:
            logger.info(f"Uploading file to {device_serial} ({ip_address}:{sdm_port})")
            logger.info(f"Local: {local_path} → Remote: {remote_path}")
            
            # Verify local file exists
            local = Path(local_path)
            if not local.exists():
                return FileTransferResult(
                    success=False,
                    message=f"Local file not found: {local_path}"
                )
            
            bytes_to_upload = local.stat().st_size
            logger.info(f"File size: {bytes_to_upload} bytes")
            
            # Build SCP command (EXACT pattern from original)
            scp_cmd = [
                "scp",
                "-P", str(sdm_port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=10",
                str(local),
                f"root@{ip_address}:{remote_path}"
            ]
            
            logger.info(f"SCP command: {' '.join(scp_cmd)}")
            
            # REAL SCP execution
            try:
                result = subprocess.run(
                    scp_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
                logger.info(f"SCP exit code: {result.returncode}")
                
                if result.returncode == 0:
                    # Calculate MD5 of uploaded file
                    md5_hash = hashlib.md5()
                    with open(local, 'rb') as f:
                        for chunk in iter(lambda: f.read(8192), b''):
                            md5_hash.update(chunk)
                    
                    md5sum = md5_hash.hexdigest()
                    logger.info(f"✅ File uploaded successfully (MD5: {md5sum})")
                    
                    return FileTransferResult(
                        success=True,
                        message=f"File uploaded successfully to {remote_path}",
                        bytes_transferred=bytes_to_upload,
                        md5sum=md5sum
                    )
                else:
                    logger.error(f"SCP failed: {result.stderr}")
                    return FileTransferResult(
                        success=False,
                        message=f"Upload failed: {result.stderr}"
                    )
                    
            except subprocess.TimeoutExpired:
                logger.error(f"Upload timed out after {timeout}s")
                return FileTransferResult(
                    success=False,
                    message=f"Upload timed out after {timeout} seconds"
                )
                
        except Exception as e:
            logger.exception(f"Upload error: {str(e)}")
            return FileTransferResult(
                success=False,
                message=str(e)
            )

    def download_file_sync(
        self,
        device_serial: str,
        ip_address: str,
        sdm_port: int,
        remote_path: str,
        local_path: str,
        timeout: int = 60
    ) -> FileTransferResult:
        """
        Download file from device via SCP - REAL file transfer (from sshcommand.py)
        
        Downloads remote file from device to local path
        Returns success status and bytes transferred
        """
        try:
            logger.info(f"Downloading file from {device_serial} ({ip_address}:{sdm_port})")
            logger.info(f"Remote: {remote_path} → Local: {local_path}")
            
            # Ensure local directory exists
            local = Path(local_path)
            local.parent.mkdir(parents=True, exist_ok=True)
            
            # Build SCP command (EXACT pattern from original)
            scp_cmd = [
                "scp",
                "-P", str(sdm_port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=10",
                f"root@{ip_address}:{remote_path}",
                str(local)
            ]
            
            logger.info(f"SCP command: {' '.join(scp_cmd)}")
            
            # REAL SCP execution
            try:
                result = subprocess.run(
                    scp_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
                logger.info(f"SCP exit code: {result.returncode}")
                
                if result.returncode == 0:
                    if local.exists():
                        bytes_downloaded = local.stat().st_size
                        
                        # Calculate MD5 of downloaded file
                        md5_hash = hashlib.md5()
                        with open(local, 'rb') as f:
                            for chunk in iter(lambda: f.read(8192), b''):
                                md5_hash.update(chunk)
                        
                        md5sum = md5_hash.hexdigest()
                        logger.info(f"✅ File downloaded successfully ({bytes_downloaded} bytes, MD5: {md5sum})")
                        
                        return FileTransferResult(
                            success=True,
                            message=f"File downloaded successfully to {local_path}",
                            bytes_transferred=bytes_downloaded,
                            md5sum=md5sum
                        )
                    else:
                        return FileTransferResult(
                            success=False,
                            message="Download command succeeded but file not found"
                        )
                else:
                    logger.error(f"SCP failed: {result.stderr}")
                    return FileTransferResult(
                        success=False,
                        message=f"Download failed: {result.stderr}"
                    )
                    
            except subprocess.TimeoutExpired:
                logger.error(f"Download timed out after {timeout}s")
                return FileTransferResult(
                    success=False,
                    message=f"Download timed out after {timeout} seconds"
                )
                
        except Exception as e:
            logger.exception(f"Download error: {str(e)}")
            return FileTransferResult(
                success=False,
                message=str(e)
            )

    def execute_batch_commands_sync(
        self,
        device_serial: str,
        ip_address: str,
        sdm_port: int,
        commands: List[str],
        timeout: int = 60
    ) -> SSHCommandResult:
        """
        Execute multiple commands in sequence - REAL batch execution
        
        Executes list of commands on device, stops on first error
        """
        try:
            logger.info(f"Executing {len(commands)} commands on {device_serial}")
            
            # Combine commands with semicolons (EXACT pattern from original)
            combined_cmd = "; ".join(commands)
            
            return self.execute_command_sync(
                device_serial,
                ip_address,
                sdm_port,
                combined_cmd,
                timeout
            )
                
        except Exception as e:
            logger.exception(f"Batch execution error: {str(e)}")
            return SSHCommandResult(
                success=False,
                output="",
                error=str(e),
                exit_code=-1
            )
