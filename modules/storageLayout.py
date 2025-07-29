from logging.handlers import RotatingFileHandler
import re
import subprocess
import json
import time
from datetime import datetime
import os
import logging
from typing import Dict


def setup_storage_logger(machine_name, log_dir="storage_layout_logs"):
    os.makedirs(log_dir, exist_ok=True)
    log_file = f"{machine_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = os.path.join(log_dir, log_file)

    logger = logging.getLogger(f"storage_logger_{machine_name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = RotatingFileHandler(log_path, maxBytes=1 * 1024 * 1024, backupCount=5)
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger

def run_maas_command(command: str, machine: str = "") -> Dict:
    """Execute MAAS CLI command with silent handling for expected errors."""
    try:
        result = subprocess.run(
            command.split(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
        if result.stderr and "not found" in result.stderr.lower():
            return {}
        if result.stderr.strip():
            raise subprocess.CalledProcessError(
                returncode=result.returncode,
                cmd=command,
                stderr=result.stderr
            )
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError):
        return {}


def parse_size_to_bytes(size_str: str) -> int:
    if not size_str:
        return 0

    size_str = size_str.strip().upper()

    match = re.match(r"([\d.]+)([KMGT]?)", size_str)
    
    if not match:
        raise ValueError(f"Invalid size string format: {size_str}")
    value = float(match.group(1))
    unit = match.group(2) # K, M, G, T or empty for bytes
    multipliers = {
        '': 1,       # Bytes (default if no unit specified)

        'K': 1024,   # Kilobytes

        'M': 1024**2, # Megabytes

        'G': 1024**3, # Gigabytes

        'T': 1024**4  # Terabytes
    }
    return int(value * multipliers.get(unit, 1))

def format_and_mount(machine_id,hostname, boot_disk, boot_part1, boot_efi_part2, vg_id,lv_config,vg_group_name, logger):
    """Handle filesystem formatting and mounting."""
    try:
        logger.info(f"{hostname}: Formatting boot partitions")
        run_maas_command(f"maas admin partition format {machine_id} {boot_disk} {boot_efi_part2} fstype=fat32", machine_id)
        run_maas_command(f"maas admin partition format {machine_id} {boot_disk} {boot_part1} fstype=ext4", machine_id)

        logger.info(f"{hostname}: Mounting boot partitions")
        run_maas_command(f"maas admin partition mount {machine_id} {boot_disk} {boot_efi_part2} mount_point=/boot/efi", machine_id)
        run_maas_command(f"maas admin partition mount {machine_id} {boot_disk} {boot_part1} mount_point=/boot", machine_id)

        # Format and mount logical volumes
        logical_volumes = run_maas_command(f"maas admin volume-group read {machine_id} {vg_id}", machine_id).get('logical_volumes', [])
        fs_type_map = {lv["name"]: lv.get("fs_type") for lv in lv_config}
        lv_mount_point_map = {lv["name"]: lv.get("mount_point") for lv in lv_config}
        for lv in logical_volumes:
            lv_id = lv.get('id')
            lv_name = lv.get('name', '')
        
            if not lv_id or not lv_name:
                continue
            base_name = lv_name[len(vg_group_name) + 1:] if lv_name.startswith(f"{vg_group_name}-") else lv_name
            fs_type = fs_type_map.get(base_name, "ext4")
            lv_mount_point = lv_mount_point_map.get(base_name, "")
            if 'swap' in base_name:
                # Format swap, do not mount
                logger.info(f"{hostname}: Formatting LV '{base_name}' as swap")
                run_maas_command(f"maas admin block-device format {machine_id} {lv_id} fstype=swap", machine_id)
                continue

            logger.info(f"{hostname}: Formatting LV '{base_name}' as {fs_type}")
            run_maas_command(f"maas admin block-device format {machine_id} {lv_id} fstype={fs_type}", machine_id)

            logger.info(f"{hostname}: Mounting LV '{base_name}' at '{lv_mount_point}'")
            run_maas_command(f"maas admin block-device mount {machine_id} {lv_id} mount_point={lv_mount_point}", machine_id)
        logger.info(f"{hostname}: Formatting and mounting completed successfully")
    except Exception as e:
        logger.error(f"{hostname}: Format/mount failed for {base_name} - {str(e)}")
        raise

def process_machine(machine_id,hostname,storage_layout_template,logger):
    try:
        with open(storage_layout_template, 'r') as f:
            lv_config_data = json.load(f)
            vg_group_name = lv_config_data.get("vg_group", "maas_vg")  # fallback default
            boot_efi_size = lv_config_data.get("boot_efi_size", "0.5G")
            boot_size = lv_config_data.get("boot_size", "1G")
            lv_config = lv_config_data.get("volumes", [])
            
        logger.info(f"{hostname}: Starting storage configuration")

        # Get boot disk
        machine_info = run_maas_command(f"maas admin machine read {machine_id}", machine_id)
        boot_disk = machine_info.get('boot_disk', {}).get('id')
        if not boot_disk:
            logger.warning(f"{hostname}: No boot disk found")
            return
        
        logger.info(f"{hostname}: Cleaning existing volume groups")
        for vg in run_maas_command(f"maas admin volume-groups read {machine_id}", machine_id):
            if vg_id := vg.get('id'):
                for lv in run_maas_command(f"maas admin volume-group read {machine_id} {vg_id}", machine_id).get('logical_volumes', []):
                    if lv_id := lv.get('id'):
                        run_maas_command(f"maas admin block-device delete {machine_id} {lv_id}", machine_id)
                run_maas_command(f"maas admin volume-group delete {machine_id} {vg_id}", machine_id)

        logger.info(f"{hostname}: Cleaning partitions on all devices")
        for device in run_maas_command(f"maas admin block-devices read {machine_id}", machine_id):
            if device_id := device.get('id'):
                for part in run_maas_command(f"maas admin partitions read {machine_id} {device_id}", machine_id):
                    if part_id := part.get('id'):
                        run_maas_command(f"maas admin partition delete {machine_id} {device_id} {part_id}", machine_id)
                        

        # Create new layout
        logger.info(f"{hostname}: Creating new partitions on boot disk {boot_disk}")
        boot_efi_size_bytes = parse_size_to_bytes(boot_efi_size)
        boot_efi_part2 = run_maas_command(
            f"maas admin partitions create {machine_id} {boot_disk} size={boot_efi_size_bytes} bootable=true",
            machine_id
        ).get('id')
        logger.info(f"{hostname}: Created /boot/efi partition (ID: {boot_efi_part2})")
        boot_size_bytes = parse_size_to_bytes(boot_size)
        boot_part1 = run_maas_command(
            f"maas admin partitions create {machine_id} {boot_disk} size={boot_size_bytes} bootable=false",
            machine_id
        ).get('id')
        logger.info(f"{hostname}: Created /boot partition (ID: {boot_part1})")

        disk_size = sum(float(re.match(r"([\d.]+)", v["size"]).group(1)) * {"G": 1, "M": 1/1024, "T": 1024}[v["size"][-1]] for v in lv_config if v["size"])
        disk_size_bytes = int(disk_size * (1024**3))
        data_part = run_maas_command(
            f"maas admin partitions create {machine_id} {boot_disk} size={disk_size_bytes}",
            machine_id
        ).get('id')

        if data_part:
            logger.info(f"{hostname}: Creating volume group {vg_group_name}")
            vg = run_maas_command(
                f"maas admin volume-groups create {machine_id} name={vg_group_name} partitions={data_part}",
                machine_id
            )

            logger.info(f"{hostname}: Loaded {len(lv_config)} LV configs from template")
            if vg_id := vg.get('id'):
                for lv in lv_config:
                    name = lv["name"]
                    size = lv["size"]
                    logger.info(f"{hostname}: Creating LV '{name}' with size {size}")
                    run_maas_command(
                        f"maas admin volume-group create-logical-volume {machine_id} {vg_id} name={name} size={size}",
                        machine_id
                    )

                logger.info(f"{hostname}: Formatting and mounting LVs")
                format_and_mount(machine_id,hostname, boot_disk, boot_part1, boot_efi_part2, vg_id,lv_config,vg_group_name, logger)

        logger.info(f"{hostname}: Storage configuration complete")

    except Exception as e:
        logger.error(f"{hostname}: Configuration failed - {str(e)}")


def create_storage_layout(system_id,hostname,storage_layout_template,maas_logger):
    logger = setup_storage_logger(hostname)
    logger.info("Starting MAAS storage configuration")
    maas_logger.info(f"{hostname}: MAAS storage configuration started")
    try:
        process_machine(system_id,hostname,storage_layout_template,logger)
        time.sleep(1)  # Stagger start slightly

    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        logger.info("MAAS storage configuration completed")




