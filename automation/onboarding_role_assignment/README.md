# Role assignment and nodesdata.yaml file automation  Role assignment and nodesdata.yaml file automation  

 

### This automation process is split into two scripts: 

- Create Inventory Script (create_inventory.py) – Retrieves VM details from MAAS and generates an inventory file. 

- Onboarding and Role Assignment Script (onboarding_dynamic.py) – Maps host configurations, validates roles, and triggers Ansible playbooks for onboarding. 

 

 

### Create inventory script (create_inventory.py): Create inventory script (create_inventory.py): 

Uses MAAS CLI to fetch deployed VM details, including IPs and network interfaces. 

Generates a structured inventory file (vm_inventory.yaml). 

 

Run the script:  



    python3 create_inventory.py 
 

This script generates the following output: 

    Generated inventory file at '/root/vm_inventory.yaml' successfully! 
 
this script will create a yaml file with three main sections: 
```yaml
172.25.1.183:   #ip which Maas can use to communicate with the machine and ssh to it 
      interfaces:
         - ens160        #interfaces that exists on the machine 
         - ens192
      roles:
          - node_onboard      # this part will be manually edited by the customer add roles	                             - persistent-storage
      persistent_storage:    #this part will be added incase persistent_storage role is added 
           backends:
                - "NEW-NFS"
```

### Node onboarding and role assignment script (onboarding_dynamic.py): Node onboarding and role assignment script (onboarding_dynamic.py): 
 

This script automates the process of fetching host configurations, validating inventory data, and generating a vars.yml file required for PCD host onboarding. It then triggers Ansible playbooks to apply the configurations. 

 
Run the script:  



    python3 onboarding_dynamic.py 
 

##### Script Functionality: Script Functionality: 

###### 1. User Input Collection 

Prompts the user to enter values for region, URL, portal, and environment (with defaults). 

###### 2. Fetching some blueprint information using API call to to match against the inventory. 
 

- Hostconfigs defined in the bluprint and the managemant interface  

- Backend storage label 
 

###### 3. Validating Inventory Data and assigns the correct host configuration. 
 
###### Validation: 

 

- Ensures each host has assigned roles; otherwise, it raises an error and stops execution. 
 

`Error: No roles defined for host 172.25.1.185. Each host must have at least one role. `

 

- Ensure that the host interface has a hostconfig configured in the blueprint; otherwise, it raises an error and stops execution.  
 

`Error: No matched hostconfig found for IP 172.25.1.183 with interfaces ['ens160'] `

 

- Ensure that a persistent_storage section is configured in the inventory file incase there is a persistent_storage role added; otherwise, it raises an error and stops execution. 
 

``Error: 'persistent_storage' section missing for host 172.25.1.185 with 'persistent-storage' role. ``

 

- If persistent_storage role and section is added in the inventory file will validate that the storage backend label exists in the blueprint, it raises an error and stops execution. 
 
`Error: Storage backend 'NEW' defined in inventory for host 172.25.1.185 is not present in the blueprint. `

###### 4. Generating vars.yml using Jinja2 

- Loads a template (vars_template.j2) and fills it with the extracted data. 

- Saves the rendered YAML to vars.yml. 

 

###### 5. Copying vars.yml to Ansible Playbook Directory 

It will copy the vars file to user_resource_examples/templates/host_onboard_data.yaml.j2 	where this file will be used by the ansible playbooks  

 

###### 6. Executing Ansible Playbooks for PCD Host Onboarding  

 Runs a series of pcdExpress commands 


#### Prerequisites: 

1. Maas cli login  

3. Clouds.yaml created in /root/.config/openstack/clouds.yaml 

5. openstackrc file created 

7. python3-openstackclient / jq installed  

9. pcd_ansible-pcd_develop directory exists 

