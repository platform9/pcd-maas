mport yaml
import subprocess
import json
from jinja2 import Environment, FileSystemLoader
import os
import argparse

#get local directory
current_dir = os.path.dirname(os.path.abspath(__file__))

#home directory:
home = os.getenv("HOME")


# Prompt user for inputs with defaults
#region = input("Enter REGION [default: jrs]: ") or "jrs"
#url = input("Enter URL [default: https://exalt-pcd-1-jrs.app.staging-pcd.platform9.com/]: ") or "https://exalt-pcd-1-jrs.app.staging-pcd.platform9.com/"
#portal = input("Enter PORTAL [default: exalt-pcd-1]: ") or "exalt-pcd-1"
#environment = input("Enter Environment [default: stage]: ") or "stage"
user = "ubuntu"

###############################################################################
#                           Argument parsing                                  #
###############################################################################
parser = argparse.ArgumentParser(description="Utility to configure PCD and enrol nodes",formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-portal", "--portal", action='store', help="takes region name as input (REQUIRED)", required=True)
parser.add_argument("-region", "--region", action='store', help="takes site name as input to form DU name. DU=<portal>-<region> (REQUIRED)", required=True)
parser.add_argument("-environment", "--environment", action='store', help="takes a string value to segregate hosts in the side. Value: STRING", required=True)
parser.add_argument("-url ", "--url", action='store', help="Set portal URL for blueprint/hostconfigs/network resources", required=True)
parser.add_argument("-setup-environment", "--setup-environment", action='store', help="Setup environment for ansible play exec and management (REQUIRED). Values: yes|no", required=True)
args = parser.parse_args()


# Define file paths
#inventory_file = "/root/vm_inventory.yaml"
inventory_file = f"{current_dir}/vm_inventory.yaml"
#output_file = "/root/vars.yml"
output_file = f"{current_dir}/vars.yml"
#template_file = "/root/vars_template.j2"
template_file = f"{current_dir}/vars_template.j2"

# Get OpenStack Token
token_result = subprocess.run(["openstack", "token", "issue", "-f", "value", "-c", "id"], capture_output=True, text=True, check=True)
token = token_result.stdout.strip()

# Fetch host configurations from the blueprint
host_config_map = {}
resmgr_url = f"{args.url}/resmgr/v2/hostconfigs/"
blueprint_url = f"{args.url}/resmgr/v2/blueprint"
headers = {"X-Auth-Token": token, "Content-Type": "application/json"}
try:
    result = subprocess.run(["curl", "-X", "GET", "-H", f"X-Auth-Token: {token}", "-H", "Content-Type: application/json", resmgr_url, "-s"],
                            capture_output=True, text=True, check=True)
    host_configs = json.loads(result.stdout)
    for config in host_configs:
        host_config_map[config["mgmtInterface"]] = config["name"]
except Exception as e:
    print(f"Error fetching host configs: {e}")
    exit(1)

# Fetch blueprint data and extract storage backend names
try:
    result = subprocess.run(["curl", "-X", "GET", "-H", f"X-Auth-Token: {token}", "-H", "Content-Type: application/json", blueprint_url, "-s"],
                            capture_output=True, text=True, check=True)
    blueprint_data = json.loads(result.stdout)

    # Extract storage backends
    storage_backends = blueprint_data[0].get('storageBackends', {})
    backend_names = []

    for backend_type, backends in storage_backends.items():
        for backend_name in backends:
            backend_names.append(backend_name)

except Exception as e:
    print(f"Error fetching blueprint data: {e}")
    exit(1)

# Load inventory from YAML
try:
    with open(inventory_file, "r") as file:
        inventory = yaml.safe_load(file)
except Exception as e:
    print(f"Error reading inventory file: {e}")
    exit(1)

# Prepare vars.yml content

vars_data = {
    "cloud": args.region,
    "url": args.url,
    "environment": args.environment,
    "hosts": {}
}


# Process the inventory and generate the host data
for ip, data in inventory.items():
    interfaces = data.get("interfaces", [])
    roles = data.get("roles", [])

    if not roles:  # Check if roles list is empty
        print(f"Error: No roles defined for host {ip}. Each host must have at least one role.")
        exit(1) 

    # Initialize a variable to store the matched hostconfig
    matched_hostconfig = None

    # Loop through interfaces and check if a matching hostconfig exists
    for intf in interfaces:
        if intf in host_config_map:
            matched_hostconfig = host_config_map[intf]
            break  # Stop once we find the first match

    if not matched_hostconfig:
        print(f"Error: No matched hostconfig found for IP {ip} with interfaces {interfaces}")
        exit(1)

    # Prepare the host data
    host_data = {
        "ansible_ssh_user": user,
        "ansible_ssh_private_key_file": f"{home}/.ssh/id_rsa",
        "roles": roles,
        "hostconfigs": matched_hostconfig,
    }

    # Add persistent storage section if present
    if "persistent-storage" in roles:
        # Ensure persistent_storage is part of the inventory
        if "persistent_storage" not in data:
            print(f"Error: 'persistent_storage' section missing for host {ip} with 'persistent-storage' role.")
            exit(1)

        persistent_storage_config = data.get("persistent_storage", {})
        host_data["persistent_storage"] = persistent_storage_config
        
        # Extract storage backends from inventory
        inventory_backends = persistent_storage_config.get("backends", [])
        for backend in inventory_backends:
            if backend not in backend_names:
                print(f"Error: Storage backend '{backend}' defined in inventory for host {ip} is not present in the blueprint.")
                exit(1)

    # Add the host entry to vars_data
    vars_data["hosts"][ip] = host_data


# Set up the Jinja2 environment and load the template file
#env = Environment(loader=FileSystemLoader('/root'))  # Set path to template directory
#template = env.get_template('vars_template.j2')  # Load the template
env = Environment(loader=FileSystemLoader(f'{current_dir}'))  # Set path to template directory
template = env.get_template('vars_template.j2')  # Load the template

# Render the template with the data
yaml_content = template.render(url=args.url, cloud=args.region, environment=args.environment, hosts=vars_data["hosts"])

# Write the rendered YAML content to the file
try:
    with open(output_file, "w") as file:
        file.write(yaml_content)
    print(f"Generated '{output_file}' successfully!")
except Exception as e:
    print(f"Error writing output file: {e}")

# Change to the target directory
#subprocess.run(["cd", "/root/pcd_ansible-pcd_develop"], shell=True, check=True)
#os.chdir("/root/pcd_ansible-pcd_develop")
os.chdir(f"{current_dir}/pcd_ansible-pcd_develop")
# Copy vars.yml file to the base template used by the Ansible playbook
subprocess.run(["cp", "-f", f"{output_file}", "user_resource_examples/templates/host_onboard_data.yaml.j2"], check=True)

# Run the PCD Ansible playbooks
subprocess.run(["./pcdExpress", "-portal", args.portal, "-region", args.region, "-env", args.environment, "-url", args.url, "-ostype", "ubuntu", "-setup-environment", args.setup_environment], check=True)

subprocess.run([
    "./pcdExpress",
    "-env-file", f"user_configs/{args.portal}/{args.region}/{args.portal}-{args.region}-{args.environment}-environment.yaml",
    "-render-userconfig", f"user_configs/{args.portal}/{args.region}/node-onboarding/{args.portal}-{args.region}-nodesdata.yaml"
], check=True)

subprocess.run([
    "./pcdExpress",
    "-env-file", f"user_configs/{args.portal}/{args.region}/{args.portal}-{args.region}-{args.environment}-environment.yaml",
    "-create-hostagents-configs", "yes"
], check=True)

subprocess.run([
    "./pcdExpress",
    "-env-file", f"user_configs/{args.portal}/{args.region}/{args.portal}-{args.region}-{args.environment}-environment.yaml",
    "-apply-hosts-onboard", "yes"
], check=True)


