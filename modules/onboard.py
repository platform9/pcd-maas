import os
import csv
import re
import subprocess
import sys
from jinja2 import Environment, FileSystemLoader

def prepare_hosts_from_csv(csv_file, ssh_user, home, logger):
    base, ext = os.path.splitext(csv_file)
    new_csv_file = f"{base}_updated{ext}"
    try:
        with open(new_csv_file, newline='') as csvfile:
            rows = list(csv.DictReader(csvfile))
    except Exception as e:
        logger.error(f"Error reading CSV: {e}")
        sys.exit(1)

    hosts = {}
    for row in rows:
        ip = row.get("ip")
        status = row.get("deployment_status")
        if ip and status == "Deployed":
            hosts[ip] = {
                "ansible_ssh_user": ssh_user,
                "ansible_ssh_private_key_file": f"{home}/.ssh/id_rsa",
                "roles": ["node_onboard"]
            }

    if not hosts:
        logger.info("No hosts to onboard. Exiting.")
        sys.exit(1)

    return hosts


# To filter and produce a new CSV for the pcdexpress onboarding operations
def process_csv(input_csv, output_csv):
    required_fields = ['region', 'environment', 'ansible_ssh_user', 'ansible_ssh_key',
                       'roles', 'hostcluster', 'persistent_storage_backends', 'hostconfigs']

    with open(input_csv, mode='r', newline='') as infile:
        reader = csv.DictReader(infile)
        headers = reader.fieldnames

        # Check for missing required header fields
        missing_fields = [field for field in required_fields if field not in headers]
        if missing_fields:
            print(f"Missing field(s): {', '.join(missing_fields)}")
            print("falling back to default mechanism")
            return False

        if 'deployment_status' not in headers:
            print("Missing required field: deployment_status")
            print("falling back to default mechanism")
            return False

        # Filter rows where deployment_status is 'Deployed' (case-insensitive)
        all_rows = list(reader)
        rows = [row for row in all_rows if row.get('deployment_status', '').strip().lower() == 'deployed']
        if not rows:
            print("No rows with deployment_status set to 'Deployed'")
            print("falling back to default mechanism")
            return False

        for i, row in enumerate(rows, start=2):  # Accounting for header line in row numbering
            roles = [r.strip() for r in row['roles'].split(',')]
            hostcluster = row['hostcluster'].strip()
            persistent_storage_backends = row['persistent_storage_backends'].strip()
            hostconfigs = row['hostconfigs'].strip()
            if 'hypervisor' in roles and not hostcluster:
                print(f"Row {i}: 'roles' has 'hypervisor' but 'hostcluster' empty")
                print("It is mandatory to have hostcluster defined when hypervisor role is assigned")
                return False
            elif 'persistent-storage' in roles and not persistent_storage_backends:
                print(f"Row {i}: 'roles' has 'persistent-storage' but 'persistent_storage_backends' empty")
                print("It is mandatory to have hostcluster defined when hypervisor role is assigned")
                return False
            elif hostcluster and 'hypervisor' not in roles:
                print(f"Row {i}: 'hostcluster' defined but 'roles' missing 'hypervisor'")
                print("Its mandatory to have hypervisor role assigned when hostcluster is defined")
                return False
            elif persistent_storage_backends and 'persistent-storage' not in roles:
                print(f"Row {i}: 'persistent_storage_backends' defined but 'roles' missing 'persistent-storage'")
                print("Its mandatory to have persistent-storage role assigned when persistent_storage_backends is defined")
                return False
            elif not hostconfigs:
                print(f"Row {i}: 'hostconfigs' is empty")
                print("Cannot proceed with empty hostconfigs")
                return False
            elif not 'hypervisor' in roles and not hostcluster:
                print(f"Row {i}: No hypervisor role assigned and 'hostcluster' empty .. proceeding..")
                continue
            elif not persistent_storage_backends and 'persistent-storage' not in roles:
                print(f"Row {i}: 'persistent_storage_backends' empty and 'persistent-storage' roles not assigned")
                print("No persistent-storage role assigned .. proceeding..")
                continue

        # All checks passed: write output CSV with required fields only
        with open(output_csv, mode='w', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=required_fields)
            writer.writeheader()
            for row in rows:
                filtered_row = {field: row[field] for field in required_fields}
                writer.writerow(filtered_row)
    return True

def check_csv_field_for_pcdexpress(input_csv):
    required_fields = ['region', 'environment', 'ansible_ssh_user', 'ansible_ssh_key',
                       'roles', 'hostcluster', 'persistent_storage_backends', 'hostconfigs']

    with open(input_csv, mode='r', newline='') as infile:
        reader = csv.DictReader(infile)
        headers = reader.fieldnames
        # Check if any required field is present
        if any(field in headers for field in required_fields):
            return True
        else:
            return False
        
def render_vars_yaml(current_dir, template_file, output_file, url, region, environment, hosts, logger):
    
    try:
        env = Environment(loader=FileSystemLoader(current_dir))
        template = env.get_template(os.path.basename(template_file))
        yaml_content = template.render(
            url=url,
            cloud=region,
            environment=environment,
            hosts=hosts
        )

        with open(output_file, "w") as f:
            f.write(yaml_content)
        logger.info(f"Generated '{output_file}' successfully!")
    except Exception as e:
        logger.error(f"Error rendering vars.yaml: {e}")
        sys.exit(1)

def start_pcd_onboarding(csv_filename, ssh_user,portal, region, environment, url,setup_env,controller_ip,onprem, logger):
    current_dir = os.getcwd()
    pcd_dir = os.path.join(current_dir, "pcd_ansible-pcd_develop")
    output_file = os.path.join(current_dir, "vars.yaml")
    template_file = os.path.join(current_dir, "vars_template.j2")
    home = os.getenv("HOME")
    hosts = prepare_hosts_from_csv(csv_filename, ssh_user, home, logger)
    output_csv = f"{pcd_dir}/nodeconfigs.csv"
    if check_csv_field_for_pcdexpress(csv_filename):
        logger.info("PCDExpress related fields found in the provided CSV. Processing CSV for PCDExpress onboarding...")
        process_csv(csv_filename, output_csv)
        run_pcd_onboarding_with_csv(portal, region, environment, url,output_file,setup_env,controller_ip,onprem, logger)
    else:
        render_vars_yaml(current_dir, template_file, output_file, url, region, environment, hosts, logger)
        os.chdir(pcd_dir)
        run_pcd_onboarding(portal, region, environment, url,output_file,setup_env,controller_ip,onprem, logger)

def run_pcd_onboarding_with_csv(portal, region, environment, url,setup_env,controller_ip,onprem, logger):
    try:
        subprocess.run([
            "./pcdExpress","-portal", portal,"-region", region,"-env", environment,"-url", url,"-ostype", "ubuntu",
            "-setup-environment", setup_env
        ], check=True)

        subprocess.run([
            "./pcdExpress",
            "-env-file", f"user_configs/{portal}/{region}/{portal}-{region}-{environment}-environment.yaml",
            "--csv", f"nodeconfigs.csv",
            "-create-hostagents-configs", "yes"
        ], check=True)

        if onprem: 
            fqdn = url.removeprefix("https://").removesuffix("/")
            fqdninfra = re.sub(r"-(.*?)\.", ".", fqdn, count=1)
            subprocess.run([
                './pcdExpress',
                '-env-file', f'user_configs/{portal}/{region}/{portal}-{region}-{environment}-environment.yaml',
                '-onprem', 'yes',
                '-ip-addr', controller_ip,
                '-fqdn', fqdn,
                '-fqdninfra', fqdninfra
            ], check=True)

        subprocess.run([
            "./pcdExpress",
            "-env-file", f"user_configs/{portal}/{region}/{portal}-{region}-{environment}-environment.yaml",
            "-apply-hosts-onboard", "yes"
        ], check=True)

    except subprocess.CalledProcessError as e:
        logger.error(f"Error during subprocess execution: {e}")
        sys.exit(1)


def run_pcd_onboarding(portal, region, environment, url,output_file,setup_env,controller_ip,onprem, logger):
    
    try:
        
        subprocess.run(["cp", "-f", output_file, "user_resource_examples/templates/host_onboard_data.yaml.j2"], check=True)

        subprocess.run([
            "./pcdExpress","-portal", portal,"-region", region,"-env", environment,"-url", url,"-ostype", "ubuntu",
            "-setup-environment", setup_env
        ], check=True)

        subprocess.run([
            "./pcdExpress",
            "-env-file", f"user_configs/{portal}/{region}/{portal}-{region}-{environment}-environment.yaml",
            "-render-userconfig", f"user_configs/{portal}/{region}/node-onboarding/{portal}-{region}-nodesdata.yaml"
        ], check=True)

        subprocess.run([
            "./pcdExpress",
            "-env-file", f"user_configs/{portal}/{region}/{portal}-{region}-{environment}-environment.yaml",
            "-create-hostagents-configs", "yes"
        ], check=True)

        if onprem: 
            fqdn = url.removeprefix("https://").removesuffix("/")
            fqdninfra = re.sub(r"-(.*?)\.", ".", fqdn, count=1)
            subprocess.run([
                './pcdExpress',
                '-env-file', f'user_configs/{portal}/{region}/{portal}-{region}-{environment}-environment.yaml',
                '-onprem', 'yes',
                '-ip-addr', controller_ip,
                '-fqdn', fqdn,
                '-fqdninfra', fqdninfra
            ], check=True)

        subprocess.run([
            "./pcdExpress",
            "-env-file", f"user_configs/{portal}/{region}/{portal}-{region}-{environment}-environment.yaml",
            "-apply-hosts-onboard", "yes"
        ], check=True)

    except subprocess.CalledProcessError as e:
        logger.error(f"Error during subprocess execution: {e}")
        sys.exit(1)

