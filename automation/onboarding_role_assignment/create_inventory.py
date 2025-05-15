import subprocess
import json
import argparse
import os
###############################################################################
#                           Argument parsing                                  #
###############################################################################
parser = argparse.ArgumentParser(description="Utility to configure PCD and enrol nodes",formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-user", "--user", action='store', help="takes maas user name as input (REQUIRED)", required=True)
args = parser.parse_args()

#get local directory
current_dir = os.path.dirname(os.path.abspath(__file__))

# Step 1: Fetch deployed machines
result = subprocess.run(["maas", f"{args.user}", "machines", "read"], capture_output=True, text=True, check=True)

# Parse JSON output
machines = json.loads(result.stdout)

# Step 2: Extract relevant information
inventory = {}

for machine in machines:
    if machine.get("status_name") == "Deployed":
        machine_interfaces = []

        for interface in machine.get("interface_set", []):
            ip_addresses = [link.get("ip_address") for link in interface.get("links", [])]
            interface_name = interface.get("name")
            machine_interfaces.append({"interface_name": interface_name, "ip_addresses": ip_addresses})

        if machine_interfaces:
            primary_ip = machine_interfaces[0]["ip_addresses"][0] if machine_interfaces[0]["ip_addresses"] else None
            if primary_ip:
                inventory[primary_ip] = {
                    "interfaces": [iface["interface_name"] for iface in machine_interfaces],
                    "roles": ["node_onboard"]
                }

# Step 3: Define a commented template section
template_section = """\
# ---------------------------- TEMPLATE SECTION ----------------------------
# This file contains the inventory of deployed MAAS machines.
# To modify, add more fields as needed based on the example below:
#
# <IP_ADDRESS>:
#   interfaces:
#     - <INTERFACE_NAME>
#   roles:
#     - "<ROLE_NAME>"
#
# Example:
# 192.168.115.50:
#   interfaces:
#     - eth0
#     - eth1
#   roles:
#     - "node_onboard"
#     - "hypervisor"
#     - "image-library"
#     - "persistent-storage"
#   persistent_storage:
#     backends:
#       - "storage-label-1"
#       - "storage-label-2"
# ---------------------------------------------------------------------------
"""

# Output inventory with correct indentation
output_file = f"{current_dir}/vm_inventory.yaml"
with open(output_file, "w") as file:
    file.write(template_section)  # Write the template section header
    for ip, data in inventory.items():
        # Write IP address section
        file.write(f"{ip}:\n")
        file.write("  interfaces:\n")
        for iface in data["interfaces"]:
            file.write(f"    - {iface}\n")
        file.write("  roles:\n")
        for role in data["roles"]:
            file.write(f"    - {role}\n")
        file.write("\n")

print(f"Generated inventory file at '{output_file}' successfully!")

