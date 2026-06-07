"""
Batch SSH — aligned with legacy ``sdm_manager_gui`` batch behaviour:
one AP after another, optional pause between APs (same idea as Tk ``time.sleep(batch_pause)``).
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DeviceConfig:
    """Device connection config - from CSV or manual entry"""

    name: str
    ip_address: str
    sdm_port: int
    serial_no: Optional[str] = None
    model: Optional[str] = None


class BatchSSHService:
    """
    Sequential batch SSH (legacy Tk style): process devices in order,
    sleep ``pause_between_aps_sec`` between devices (default 0.15s, max 5s).
    """

    def __init__(self, jump_host: str, jump_port: int, ssh_key: Path):
        self.jump_host = jump_host
        self.jump_port = jump_port
        self.ssh_key = ssh_key
        self.cancel_flag = threading.Event()
        logger.info("BatchSSHService initialized (sequential AP processing): %s:%s", jump_host, jump_port)

    def _build_ssh_cmd(self, device: DeviceConfig, command: str) -> List[str]:
        return [
            "ssh",
            "-p",
            str(self.jump_port),
            "-i",
            str(self.ssh_key),
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            "ConnectTimeout=10",
            "-o",
            f"ProxyCommand=ssh -p {self.jump_port} -i {self.ssh_key} -W %h:%p {self.jump_host}",
            f"root@{device.ip_address}",
            command,
        ]

    def execute_batch(
        self,
        devices: List[DeviceConfig],
        command: str,
        progress_callback: Optional[Callable[[str, str], None]] = None,
        *,
        pause_between_aps_sec: float = 0.15,
    ) -> List[Dict]:
        """Run the same SSH command on each device, one device at a time (legacy Tk style)."""
        self.cancel_flag.clear()
        if not devices:
            return []

        batch_pause = max(0.0, min(5.0, float(pause_between_aps_sec)))
        results: List[Dict] = []

        for idx, device in enumerate(devices):
            if self.cancel_flag.is_set():
                break
            results.append(self._run_device_ssh_command(device, command, progress_callback))
            if batch_pause > 0 and idx < len(devices) - 1 and not self.cancel_flag.is_set():
                time.sleep(batch_pause)

        ok = len([r for r in results if r.get("success")])
        logger.info("Batch execution complete: %s/%s succeeded", ok, len(devices))
        return results

    def _run_device_ssh_command(
        self,
        device: DeviceConfig,
        command: str,
        progress_callback: Optional[Callable[[str, str], None]],
    ) -> Dict:
        device_key = f"{device.name}({device.ip_address}:{device.sdm_port})"

        if progress_callback:
            progress_callback(device_key, "Connecting...")

        ssh_cmd = self._build_ssh_cmd(device, command)

        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            success = result.returncode == 0

            if progress_callback:
                status = "✅ Success" if success else "❌ Failed"
                progress_callback(device_key, status)

            logger.info("%s: Command %s", device_key, "succeeded" if success else "failed")

            return {
                "device": device.name,
                "ip": device.ip_address,
                "success": success,
                "output": result.stdout[:500] if success else result.stderr[:500],
                "exit_code": result.returncode,
            }

        except subprocess.TimeoutExpired:
            if progress_callback:
                progress_callback(device_key, "❌ Timeout")
            return {
                "device": device.name,
                "ip": device.ip_address,
                "success": False,
                "output": "Command timed out",
                "exit_code": -1,
            }

    def cancel(self) -> None:
        """Cancel ongoing operations"""
        self.cancel_flag.set()
        logger.info("Batch operations cancelled")
