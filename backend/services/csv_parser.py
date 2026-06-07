"""
CSV Device Parser - Real logic from original
Parses device inventory from CSV for batch operations
"""

import logging
import csv
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DeviceEntry:
    """Single device entry from CSV"""
    name: str
    ip_address: str
    sdm_port: int
    serial_no: Optional[str] = None
    model: Optional[str] = None
    sdm_status: Optional[str] = None


class CSVParser:
    """
    Parse device CSV inventory
    Real logic: Field detection, validation, manual entry support
    """
    
    # Common field name variations
    PORT_FIELDS = ["SDM Port", "Port", "port", "sdm_port", "sdm-port"]
    IP_FIELDS = ["IP Address", "IP", "ip", "ip_address", "ipAddress"]
    NAME_FIELDS = ["Name", "name", "Device Name", "device_name", "deviceName"]
    SERIAL_FIELDS = ["Serial", "serial", "Serial No", "serialNo", "serial_no"]
    MODEL_FIELDS = ["Model", "model", "Device Model", "deviceModel"]
    STATUS_FIELDS = ["SDM Status", "Status", "status", "sdm_status"]

    @staticmethod
    def _find_field(row: Dict[str, str], field_options: List[str]) -> Optional[str]:
        """Find field value by checking multiple possible field names"""
        for option in field_options:
            if option in row and row[option]:
                return row[option]
        return None

    @staticmethod
    def parse_csv(csv_path: Path) -> tuple[List[DeviceEntry], List[str]]:
        """
        Parse CSV file and return device entries
        Real logic: Flexible field detection, error reporting
        """
        devices = []
        errors = []

        if not csv_path.exists():
            errors.append(f"CSV file not found: {csv_path}")
            return devices, errors

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                if not reader.fieldnames:
                    errors.append("CSV file is empty")
                    return devices, errors

                for row_num, row in enumerate(reader, start=2):  # Start at 2 (skip header)
                    try:
                        # Find port (required)
                        port_str = CSVParser._find_field(row, CSVParser.PORT_FIELDS)
                        if not port_str:
                            errors.append(f"Row {row_num}: Missing SDM Port")
                            continue

                        try:
                            port = int(port_str)
                            if not (1 <= port <= 65535):
                                errors.append(f"Row {row_num}: Invalid port {port} (must be 1-65535)")
                                continue
                        except ValueError:
                            errors.append(f"Row {row_num}: Port '{port_str}' is not a number")
                            continue

                        # Find IP (required)
                        ip = CSVParser._find_field(row, CSVParser.IP_FIELDS)
                        if not ip:
                            errors.append(f"Row {row_num}: Missing IP Address")
                            continue

                        # Find name (optional, generate if missing)
                        name = CSVParser._find_field(row, CSVParser.NAME_FIELDS)
                        if not name:
                            name = f"Device_{port}"

                        # Find optional fields
                        serial = CSVParser._find_field(row, CSVParser.SERIAL_FIELDS)
                        model = CSVParser._find_field(row, CSVParser.MODEL_FIELDS)
                        status = CSVParser._find_field(row, CSVParser.STATUS_FIELDS)

                        device = DeviceEntry(
                            name=name.strip(),
                            ip_address=ip.strip(),
                            sdm_port=port,
                            serial_no=serial.strip() if serial else None,
                            model=model.strip() if model else None,
                            sdm_status=status.strip() if status else None
                        )

                        devices.append(device)
                        logger.info(f"Row {row_num}: Parsed device {device.name} ({device.ip_address}:{device.sdm_port})")

                    except Exception as e:
                        errors.append(f"Row {row_num}: Error parsing row - {str(e)}")
                        continue

        except Exception as e:
            errors.append(f"Error reading CSV: {str(e)}")

        logger.info(f"CSV Parse complete: {len(devices)} devices, {len(errors)} errors")
        return devices, errors

    @staticmethod
    def validate_devices(devices: List[DeviceEntry]) -> tuple[List[DeviceEntry], List[str]]:
        """
        Validate device entries
        Real logic: Check for duplicates, invalid IPs, port conflicts
        """
        valid_devices = []
        errors = []
        seen_ports = {}

        for device in devices:
            # Check for duplicate ports
            key = f"{device.ip_address}:{device.sdm_port}"
            if key in seen_ports:
                errors.append(f"Duplicate device: {device.name} and {seen_ports[key]} both on {key}")
                continue

            seen_ports[key] = device.name

            # Basic IP validation
            try:
                parts = device.ip_address.split('.')
                if len(parts) != 4:
                    errors.append(f"{device.name}: Invalid IP format '{device.ip_address}'")
                    continue

                for part in parts:
                    octet = int(part)
                    if not (0 <= octet <= 255):
                        errors.append(f"{device.name}: IP octet {octet} out of range")
                        continue

            except ValueError:
                errors.append(f"{device.name}: Invalid IP address '{device.ip_address}'")
                continue

            valid_devices.append(device)

        logger.info(f"Validation complete: {len(valid_devices)} valid, {len(errors)} errors")
        return valid_devices, errors

    @staticmethod
    def devices_to_dict(devices: List[DeviceEntry]) -> List[Dict]:
        """Convert devices to dictionary format for JSON response"""
        return [
            {
                "name": d.name,
                "ip_address": d.ip_address,
                "sdm_port": d.sdm_port,
                "serial_no": d.serial_no,
                "model": d.model,
                "sdm_status": d.sdm_status
            }
            for d in devices
        ]
