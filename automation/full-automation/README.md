# Adding and deploying a machine to MAAS server, then PCD joining with an automated script 
 

### This automation process is split into two sections: 

- Automate the process of enrolling baremetals into MaaS 
- Onboarding is done by triggering Ansible playbooks. 

 

 

### How to use?

Download the script and prerequisite files into the same directory.

Script directory structure:
```bash
 .
 ├── cloud-init_tempalte.yaml
 ├── machines_tempalte.csv
 ├── vars_template.j2
 ├── main_script.py
 ├── modules
 │   ├── maasHelper.py  ---> add and deploy machines to MAAS
 │   ├── onboard.py     ---> onboard machines to PCD
 ├── pcd_ansible-pcd_develop
 │   ├── .....
 │   ├── setup-local.sh ---> Set up the  environment for PCD onboarding
```



#### Prerequisites: 
    
1. Maas cli login
 
        maas login <maas_user> http://<maas_ip>:5240/MAAS/ $(sudo maas apikey --generate --username=<maas_user>)

2. Clouds.yaml created in /{home}/.config/openstack/clouds.yaml
   ```bash
        clouds:
          titan:
            auth:
             auth_url: https://<DU-name>.app.staging-pcd.platform9.com/keystone/v3
             project_name: service
             username: abc@ACME.com
             password: *********
             user_domain_name: default
             project_domain_name: default
            region_name: titan
            interface: public
            identity_api_version: 3
            compute_api_version: 2
            volume_api_version: 3
            image_api_version: 2
            identity_interface: public
            volume_interface: public
   ```
3. untar the prerequisites file 
   ```bash
   tar -xzvf prerequisites.tar.gz
   ```
4. Set up the  environment for PCD onboarding by running the script setup-local.sh from inside pcd_ansible-pcd_develop directory.
   ```bash
   sudo bash setup-local.sh
   ```
       
 5. You need to create/edit the following files according to your environment before running the script You can use the templates provided in the prerequisites folder:

       1. machines_template.csv
          ```bash
          hostname,architecture,mac_addresses,power_type,power_user,power_pass,power_driver,power_address,cipher_suite_id,power_boot_type,privilege_level,k_g,IP,storage_ip
          pf9-test001,amd64/generic,3c:fd:fe:b5:1a:8d,ipmi,admin,password,LAN_2_0,172.25.1.11,3,auto,ADMIN,,192.168.125.167,192.168.125.165
          pf9-test002,amd64/generic,3c:fd:fe:b5:1a:8d,ipmi,admin,password,LAN_2_0,172.25.1.12,3,auto,ADMIN,,192.168.125.168,192.168.125.166
          ```
       3. cloud-init-template.yaml
          - The only requirement for this file is to have the IP and the storage_ip  as a placeholder to be filled in dynamically for each machine 
          ```bash
          #cloud-config
          write_files:
            - path: /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
              permissions: "0644"
              content: |
                network: {config: disabled}
          
            - path: /etc/netplan/99-custom.yaml
              permissions: "0644"
              content: |
                network:
                  version: 2
                  renderer: networkd
                  ethernets:
                    enp94s0f0:
                      dhcp4: false
                    enp24s0f1:
                      dhcp4: false
                  bonds:
                    bond0:
                      interfaces:
                        - enp24s0f1
                        - enp94s0f0
                      parameters:
                        mode: active-backup
                        primary: enp24s0f1
                        mii-monitor-interval: 100
                      dhcp4: false
                      addresses:
                        - $ip/24    --> placeholder for the IP
                      routes:
                        - to: default
                          via: 192.168.125.254
                      nameservers:
                        addresses:
                          - 8.8.8.8
                  vlans:
                    vlan.301:  
                      id: 301  
                      link: bond0 
                      addresses:  
                        - $storage_ip/18     --> placeholder for the storage IP
                      routes:  
                        - to: default  
                          via: 10.10.0.1  
                      nameservers:  
                        addresses:  
                          - 8.8.8.8 
                          - 1.1.1.1 
          ``` 
          
  6. Ensure the SSH key for the MAAS server user (used to connect to deployed machines during onboarding) is added in the MAAS UI.
        
#### Run the script:  

```bash
    python3 main_script.py \
    --maas_user admin \
    --csv_filename machines.csv \
    --cloud_init_template cloud-init.yaml \
    --portal exalt-pcd \
    --region jrs \
    --environment stage \
    --url https://exalt-pcd-jrs.app.qa-pcd.platform9.com/ \
    --max_workers 5 \
    --ssh_user ubuntu \
    --setup_env yes
```
What the options mean:
  - ```--maas_user```: MAAS admin username.
  - ```--csv_filename```: CSV file path.
  - ```--cloud_init_template```: Cloud-init template YAML path.
  - ```--max_workers```: Maximum number of concurrent threads for provisioning.
  - ```--ssh_user```: SSH user for Ansible.
  - ```--setup_env```: By default, it's no, but for the first run on the maas machine, it should be yes to set up the necessary directories

    
There is an optional argument:
  - ```--preserve_cloud_init```: By default, it's no, but when set to yes, it will keep all generated cloud-init files under
    ```bash
    /{script directory}/maas-cloud-init/cloud-init-{hostname}.yaml
    ```

Script directory structure after running the script:
```bash
 .
 ├── cloud-init_tempalte.yaml
 ├── maas-cloud-init
 │   └── cloud-init-{hostname}.yaml    ---> generated cloud-init files for each machine
 ├── deploy_logs
 │   └── maas_deployment.log           ---> generated logs for MAAS 
 ├── machines_tempalte.csv
 ├── {your CSV file name}_updated.csv  ---> updated csv with the status of the deployment
 ├── vars_template.j2
 ├── vars.yaml                         ---> yaml file that will be used by the onboarding Ansible playbooks
 ├── main_script.py
 ├── modules
 │   ├── maasHelper.py  
 │   ├── onboard.py     
 ├── pcd_ansible-pcd_develop
 │   ├── .....
 │   ├── logs
 │   │   └── pcd_installer_logs
 │   ├── setup-local.sh 
```
 
#### Script Functionality: 

##### 1. It will add the machines to MAAS and commission them.

##### 2. Deploy the machines once the state is ready 
When in ready state, it will generate a cloud-init file for each machine with the IP specified for each one from the CSV file,it will be generated in the tmp directory,and then deploy the OS.
```bash
/maas-cloud-init/cloud-init-{hostname}.yaml
```
Those files will be deleted once the deployment is done, unless the flag preserve_cloud_init is set to yes
##### 3. After the deployment is done and successful, the onboarding process will begin. 
After deployment, a new CSV file will be generated that contains all the previous info along with the deployment status to ensure that undeployed or uncommissioned machines don't go through the onboarding phase.
```bash
{your CSV file name}_updated.csv
```
##### 4. Will start by generating a vars.yaml file, which contains all the necessary information about each host, using Jinja2 
  - Loads a template (vars_template.j2) and fills it with the extracted data. 
  - Saves the rendered YAML to vars.yaml.
    
sample vars.yaml:
```bash
url: https://exalt-pcd-jrs.app.qa-pcd.platform9.com/
cloud: jrs
environment: stage
hosts:
  192.168.125.165:
    ansible_ssh_user: "ubuntu"
    ansible_ssh_private_key_file: "/home/exalt/.ssh/id_rsa"
    roles:
      - "node_onboard"
``` 

##### 5. Copying vars.yml to Ansible Playbook Directory 
It will copy the vars file to user_resource_examples/templates/host_onboard_data.yaml.j2, where the Ansible playbooks will use this file  


##### 6. Executing Ansible Playbooks for PCD Host Onboarding  






