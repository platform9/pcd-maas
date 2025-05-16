import os
import csv
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

def start_pcd_onboarding(csv_filename, ssh_user,portal, region, environment, url,setup_env, logger):
    current_dir = os.getcwd()
    output_file = os.path.join(current_dir, "vars.yaml")
    template_file = os.path.join(current_dir, "vars_template.j2")
    home = os.getenv("HOME")
    hosts = prepare_hosts_from_csv(csv_filename, ssh_user, home, logger)
    pcd_dir = os.path.join(current_dir, "pcd_ansible-pcd_develop")
    render_vars_yaml(current_dir, template_file, output_file, url, region, environment, hosts, logger)
    os.chdir(pcd_dir)
    run_pcd_onboarding(portal, region, environment, url,output_file,setup_env, logger)

def run_pcd_onboarding(portal, region, environment, url,output_file,setup_env, logger):
    
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

        subprocess.run([
            "./pcdExpress",
            "-env-file", f"user_configs/{portal}/{region}/{portal}-{region}-{environment}-environment.yaml",
            "-apply-hosts-onboard", "yes"
        ], check=True)

    except subprocess.CalledProcessError as e:
        logger.error(f"Error during subprocess execution: {e}")
        sys.exit(1)
