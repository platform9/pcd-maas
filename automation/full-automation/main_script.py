import argparse
import os
import sys
from modules import maasHelper, onboard 
import time



###############################################################################
#                           Argument parsing                                  #
###############################################################################
parser = argparse.ArgumentParser(description="Add and deploy MAAS machines from a CSV file.and PCD Node Onboarding")
parser.add_argument("-maas_user","--maas_user", required=True, help="MAAS username")
parser.add_argument("-csv_filename","--csv_filename", required=True, help="CSV file path")
parser.add_argument("-cloud_init_template", "--cloud_init_template", required=True, help="Cloud-init template YAML path ")
parser.add_argument("-portal", "--portal", required=True, help="Region name (REQUIRED)")
parser.add_argument("-region", "--region", required=True, help="Site name to form DU=<portal>-<region> (REQUIRED)")
parser.add_argument("-environment", "--environment", required=True, help="Environment name to segregate hosts")
parser.add_argument("-url", "--url", required=True, help="Portal URL for blueprint/hostconfigs/network resources")
parser.add_argument("-ssh_user", "--ssh_user", required=True, help="SSH user for Ansible")
parser.add_argument("-max_workers", "--max_workers", required=True,type=int,help="Maximum number of concurrent threads for provisioning")
parser.add_argument("-preserve_cloud_init","--preserve_cloud_init",choices=["yes", "no"],default="no",help="Preserve cloud-init files created for each machine (yes or no, default: no)")
parser.add_argument("-setup_env","--setup_env",choices=["yes", "no"],default="no",help="setup the environment for pcd onboarding script (yes or no, default: no)")
args = parser.parse_args()


current_dir = os.getcwd()
home = os.getenv("HOME")
logger = maasHelper.setup_logger()


if not os.path.isfile(args.cloud_init_template):
    logger.error(f"Error: The cloud-init template file '{args.cloud_init_template}' does not exist.")
    sys.exit(1)
if not os.path.isfile(args.csv_filename):
    logger.error(f"Error: The CSV file '{args.csv_filename}' does not exist.")
    sys.exit(1)
if not os.path.isfile("vars_template.j2"):
    logger.error(f"Error: The template file vars_template.j2 does not exist.")
    sys.exit(1)
if not os.path.isdir("pcd_ansible-pcd_develop"):
    logger.error(f"Directory pcd_ansible-pcd_develop does not exist.")
    sys.exit(1)
###############################################################################
#                        Deploy MAAS machines from CSV                        #
###############################################################################
logger.info("Starting deployment of baremetal nodes...")
maasHelper.add_machines_from_csv(
    args.csv_filename,
    args.maas_user,
    args.max_workers,
    args.cloud_init_template,
    args.preserve_cloud_init,
    logger
)

logger.info("Waiting 20 seconds for the machines and their interfaces to be up before starting onboarding...")
time.sleep(20)
###############################################################################
#                      Load CSV rows and filter deployed                      #
###############################################################################

onboard.start_pcd_onboarding(
    csv_filename=args.csv_filename,
    ssh_user=args.ssh_user,
    portal=args.portal,
    region=args.region,
    environment=args.environment,
    url=args.url,
    setup_env=args.setup_env,
    logger=logger
)
