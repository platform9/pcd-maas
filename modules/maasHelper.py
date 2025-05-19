
import os
import sys
import csv
import json
import time
import logging
from string import Template
from datetime import datetime
import subprocess
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor

def setup_logger(log_name="maas_logger", log_dir="deploy_logs", log_file="maas_deployment.log"):
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)
    logger = logging.getLogger(log_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = RotatingFileHandler(log_path, maxBytes=1 * 1024 * 1024, backupCount=5)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

def add_machines_from_csv(csv_file,maas_user,max_workers,cloud_init_template,preserve_cloud_init, logger):
    try:
        with open(csv_file, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
        
        # Create machines
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(create_machine, maas_user, row,logger) for row in rows]
            results = [f.result() for f in futures]

        # Deploy machines
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            executor.map(lambda args: configure_and_deploy(maas_user, *args, cloud_init_template,preserve_cloud_init,logger), results)
        
        save_csv(csv_file,rows,logger)

    except Exception as e:
        logger.error(f"Error reading CSV file: {str(e)}")
        raise

def get_machine_status(maas_user, system_id):
    result = subprocess.run(["maas", maas_user, "machine", "read", system_id], capture_output=True, text=True)
    if result.returncode == 0:
        machine_info = json.loads(result.stdout)
        return machine_info.get("status_name", "Unknown")
    return "Unknown"

def wait_for_status(maas_user, system_id, expected_status, hostname,logger, timeout=600, interval=30):
    elapsed = 0
    while elapsed < timeout:
        status = get_machine_status(maas_user, system_id)
        logger.info(f"[{hostname}] Status: {status}")
        if status == "Failed commissioning" or status == "Unknown":
            return False
        if status == expected_status:
            return True
        time.sleep(interval)
        elapsed += interval
    logger.warning(f"[{hostname}] Timeout waiting for status: {expected_status}")
    return False

def generate_cloud_init(template_file, output_file, ip, storage_ip):
    with open(template_file, 'r') as f:
        template = Template(f.read())
    rendered = template.safe_substitute(ip=ip, storage_ip=storage_ip)
    with open(output_file, 'w') as f:
        f.write(rendered)

def create_machine(maas_user, row,logger):
    hostname = row["hostname"]
    architecture = row["architecture"]
    mac_addresses = row["mac_addresses"]
    power_type = row["power_type"]

    power_parameters = {
        "power_user": row["power_user"],
        "power_pass": row["power_pass"],
        "power_driver": row["power_driver"],
        "power_address": row["power_address"],
        "cipher_suite_id": row["cipher_suite_id"],
        "power_boot_type": row["power_boot_type"],
        "privilege_level": row["privilege_level"],
        "k_g": row["k_g"]
    }

    create_command = [
        "maas", maas_user, "machines", "create",
        f"hostname={hostname}",
        f"architecture={architecture}",
        f"mac_addresses={mac_addresses}",
        f"power_type={power_type}",
        f"power_parameters={json.dumps(power_parameters)}"
    ]

    try:
        result = subprocess.run(create_command, check=True, capture_output=True, text=True)
        logger.info(f"[{hostname}] Machine created.")
        response = json.loads(result.stdout)
        return hostname, response.get("system_id"), row
    except subprocess.CalledProcessError as e:
        logger.error(f"[{hostname}] Error creating machine:{e.returncode}")
        logger.error(f"STDERR: {e.stderr.strip()}")
        logger.error(f"STDOUT: {e.stdout.strip()}")
        return hostname, None, row

def configure_and_deploy(maas_user, hostname, system_id, row, cloud_init_template,preserve_cloud_init,logger):
    if not system_id:
        logger.warning(f"[{hostname}] Skipping: no system_id.")
        row["deployment_status"] = "System ID Missing Machine Was Not Created"
        return

    if wait_for_status(maas_user, system_id, "Ready", hostname,logger, 600, 30):
        current_dir = os.getcwd()
        temp_cloud_init_dir = os.path.join(current_dir, "maas-cloud-init")
        os.makedirs(temp_cloud_init_dir, exist_ok=True)
        temp_cloud_init = f"{temp_cloud_init_dir}/cloud-init-{hostname}.yaml"
        generate_cloud_init(cloud_init_template, temp_cloud_init, row["ip"], row["storage_ip"])
        try:
            deploy_command = f'maas {maas_user} machine deploy {system_id} user_data="$(base64 -w 0 {temp_cloud_init})"'
            subprocess.run(deploy_command, shell=True, check=True, capture_output=True, text=True)
            logger.info(f"[{hostname}] Deploy triggered with cloud-init.")
        except subprocess.CalledProcessError as e:
            logger.error(f"[{hostname}] Deploy failed:{e.returncode}")
            logger.error(f"STDERR: {e.stderr.strip()}")
            logger.error(f"STDOUT: {e.stdout.strip()}")
            row["deployment_status"] = "Deploy Failed"
            os.remove(temp_cloud_init)
            return

        if wait_for_status(maas_user, system_id, "Deployed", hostname,logger, 1200, 60):
            logger.info(f"[{hostname}] Deployment completed.")
            update_ipmi_user(system_id, hostname,maas_user, row)
            row["deployment_status"] = "Deployed"
        else:
            logger.warning(f"[{hostname}] Did not reach Deployed state.")
            row["deployment_status"] = "Deployment Timeout"
        if preserve_cloud_init == "no" and os.path.exists(temp_cloud_init):
            os.remove(temp_cloud_init)
    else:
        logger.warning(f"[{hostname}] Not Ready. Skipping deployment.")
        row["deployment_status"] = "Not Ready,Commissioning Was Not Done"

def update_ipmi_user(system_id, hostname,maas_user, row):
    power_params = json.dumps({
        "power_user": row["power_user"],
        "power_pass": row["power_pass"]
    })
    update_command = [
        "maas", maas_user, "machine", "update", system_id,
        f"power_parameters={power_params}"
    ]
    try:
        subprocess.run(update_command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to update IPMI user for {hostname}: {str(e)}")

def save_csv(csv_file, rows, logger):
    base, ext = os.path.splitext(csv_file)
    new_csv_file = f"{base}_updated{ext}"
    fieldnames = list(rows[0].keys())
    if "deployment_status" not in fieldnames:
        fieldnames.append("deployment_status")

    try:
        with open(new_csv_file, "w", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Updated CSV with deployment status at {new_csv_file}")
    except Exception as e:
        logger.error(f"Error writing to CSV: {str(e)}")

