wiper
=====

Wipe and reprovision a Cisco ACI APIC over CIMC Serial Over LAN.

Install
-------

Option 1
^^^^^^^^

Easy install from pypi::

    easy_install wiper

Option 2
^^^^^^^^

Clone the repo and run setup.py to install::

    git clone https://github.com/datacenter/wiper.git
    cd wiper
    python setup.py install

Run
---

Once installed, this package adds both 'apic_wiper' and 'wiper' to the bin directory for python install/virtual environment.

Options for config arguments
----------------------------

Options can be set via the CLI as command line arguments or in an ini file that is specified with
the -i/--ini-file option.  The order of precedence is as follows:

1. CLI options override all options set elsewhere.
2. INI file options for a specific APIC override default options specified in the INI file.
3. INI file options in a DEFAULT section will be used as a last resort if that option is not
   specified elsewhere.
4. Any missing options will result in the script not running.

Because there are so many required options it is highly recommended that options be set in an INI
file.

The following is a table of required config arguments:

    +--------------------------+---------------+-----------------------+
    |       **Long CLI**       | **Short CLI** | **INI File**          |
    |        **Option**        |  **Option**   |  **Option**           |
    +--------------------------+---------------+-----------------------+
    |  --controller-number     |     -cnu      | controller_number     |
    +--------------------------+---------------+-----------------------+
    |  --strong-passwords      |     -sp       | strong_passwords      |
    +--------------------------+---------------+-----------------------+
    |  --infra-vlan-id         |     -iv       | infra_vlan_id         |
    +--------------------------+---------------+-----------------------+
    |  --fabric-name           |     -f        | fabric_name           |
    +--------------------------+---------------+-----------------------+
    |  --cimc-username         |     -cu       | cimc_username         |
    +--------------------------+---------------+-----------------------+
    |  --controller-name       |     -cna      | controller_name       |
    +--------------------------+---------------+-----------------------+
    |  --apic-admin-password   |     -ap       | apic_admin_password   |
    +--------------------------+---------------+-----------------------+
    |  --bd-mc-addresses       |     -b        | bd_mc_addresses       |
    +--------------------------+---------------+-----------------------+
    |  --cimc-password         |     -cp       | cimc_password         |
    +--------------------------+---------------+-----------------------+
    |  --oob-default-gateway   |     -od       | oob_default_gateway   |
    +--------------------------+---------------+-----------------------+
    |  --int-speed             |     -is       | int_speed             |
    +--------------------------+---------------+-----------------------+
    |  --oob-ip-address        |     -oi       | oob_ip_address        |
    +--------------------------+---------------+-----------------------+
    |  --tep-address-pool      |     -t        | tep_address_pool      |
    +--------------------------+---------------+-----------------------+
    |  --number-of-controllers |     -nc       | number_of_controllers |
    +--------------------------+---------------+-----------------------+

CLI Options
-----------

The only required CLI option is the CIMC IP address which is used to log into CIMC.  All other
options can also be set via an INI file.  CLI options override the same option set in an INI file.

Wiper has the following CLI options::

   $ wiper -h
   usage: Provision APICs via CIMC Serial Over LAN [-h] [-ap APIC_ADMIN_PASSWORD]
                                                   [-b BD_MC_ADDRESSES]
                                                   [-cna CONTROLLER_NAME]
                                                   [-cnu CONTROLLER_NUMBER]
                                                   [-cp CIMC_PASSWORD]
                                                   [-cu CIMC_USERNAME]
                                                   [-i INI_FILE]
                                                   [-is {auto,10baseT/Half,10baseT/Full,100baseT/Half,100baseT/Full,1000baseT/Full}]
                                                   [-iv INFRA_VLAN_ID]
                                                   [-f FABRIC_NAME]
                                                   [-nc NUMBER_OF_CONTROLLERS]
                                                   [-od OOB_DEFAULT_GATEWAY]
                                                   [-oi OOB_IP_ADDRESS] [-sim]
                                                   [-sp {Y,n}]
                                                   [-t TEP_ADDRESS_POOL] [-v]
                                                   cimc_ip
    
   positional arguments:
       cimc_ip               CIMC hostname or IP address used to ssh to CIMC

   optional arguments:
       -h, --help            show this help message and exit
       -ap APIC_ADMIN_PASSWORD, --apic_admin_password APIC_ADMIN_PASSWORD
                             The APIC admin user password to enter into the APIC
                             setup script.
       -b BD_MC_ADDRESSES, --bd-mc-addresses BD_MC_ADDRESSES
                             The Bridge Domain Multicast address range to enter
                             into the APIC setup script.
       -cna CONTROLLER_NAME, --controller-name CONTROLLER_NAME
                             The controller name to enter into the APIC setup
                             script.
       -cnu CONTROLLER_NUMBER, --controller_number CONTROLLER_NUMBER
                             The controller number (id) to enter into the APIC
                             setup script.
       -cp CIMC_PASSWORD, --cimc_password CIMC_PASSWORD
                             CIMC password
       -cu CIMC_USERNAME, --cimc_username CIMC_USERNAME
                             CIMC username
       -i INI_FILE, --ini-file INI_FILE
                             Use an ini file to find parameters to provision an
                             APIC.
       -is {auto,10baseT/Half,10baseT/Full,100baseT/Half,100baseT/Full,1000baseT/Full}, --int-speed {auto,10baseT/Half,10baseT/Full,100baseT/Half,100baseT/Full,1000baseT/Full}
       -iv INFRA_VLAN_ID, --infra-vlan-id INFRA_VLAN_ID
                             The infra vlan id to enter into the APIC setup script.
       -f FABRIC_NAME, --fabric-name FABRIC_NAME
                             The fabric name to enter into the APIC setup script.
       -nc NUMBER_OF_CONTROLLERS, --number-of-controllers NUMBER_OF_CONTROLLERS
                             The number of controllers to enter into the APIC setup
                             script.
       -od OOB_DEFAULT_GATEWAY, --oob-default-gateway OOB_DEFAULT_GATEWAY
                             The APIC Out-Of-Band default gateway to enter into the
                             APIC setup script.
       -oi OOB_IP_ADDRESS, --oob-ip-address OOB_IP_ADDRESS
                             The APIC Out-Of-Band IP address to enter into the APIC
                             setup script.
       -sim, --simulator     This flag identifies the APIC as a simulator.
       -sp {Y,n}, --strong-passwords {Y,n}
                             Strong password option to enter into the APIC setup
                             script.
       -t TEP_ADDRESS_POOL, --tep-address-pool TEP_ADDRESS_POOL
                             The TEP address pool to enter into the APIC setup
                             script.
       -v, --verbose         Enable debugging and be verbose.

INI file options
----------------

The following is a **recommended** ini file::

    ; These default settings can be modified to allow for different defaults for your environment.
    ; You can override these defaults in sections for specific controllers.
    [DEFAULT]
    ; Simulators are not currently supported but the plan is to eventually support them if possible
    ; So this is in preparation of that.
    simulator = False
    ; A default cimc user to access the Serial Over LAN with
    cimc_username = admin
    ; A default cimc password
    cimc_password = password
    ; The default fabric name.
    fabric_name = ACI Fabric1
    ; The default controller number.
    controller_number = 1
    ; The default number of controllers for all clusters.
    number_of_controllers = 3
    ; The default controller name is 'apic' + the controller id.  So for controller 1, the default
    ; name is apic1.  For controller 2 the default name is apic2, etc.
    controller_name = apic%(controller_number)s
    ; The default tep address pool.
    tep_address_pool = 10.0.0.0/16
    ; The default infra vlan id.
    infra_vlan_id = 4093
    ; The default BD Multicast Address pool
    bd_mc_addresses = 225.0.0.0/15
    ; The default oob ip address and netmask in the firm x.x.x.x/y
    oob_ip_address = 192.168.10.1/24
    ; The default oob default gateway ip address.
    oob_default_gateway = 192.168.10.254
    ; The default interface speed and duplex, we default to auto
    int_speed = auto
    ; By default we require strong passwords
    strong_passwords = Y
    ; A default admin password.  Usually the individual apic configs will override this.
    apic_admin_password = p@s$w0rd
     
    ; Sections are defined by the cimc ip address, items defined in sections override the default items
    [172.16.176.191]
    fabric_name = 176_fabric3
    cimc_password = Cisco123!
    controller_number = 1
    oob_ip_address = 172.16.176.192/24
    oob_default_gateway = 172.16.176.1
    apic_admin_password = Cisco321!
    
    ; Multiple CIMC's can be defined in the ini file
    [172.16.176.193]
    fabric_name = 176_fabric3
    cimc_password = Cisco123!
    controller_number = 2
    oob_ip_address = 172.16.176.194/24
    oob_default_gateway = 172.16.176.1
    ; apic password is not needed for controllers 2 and 3
    
    ; Multiple CIMC's can be defined in the ini file
    [172.16.176.195]
    fabric_name = 176_fabric3
    cimc_password = Cisco123!
    controller_number = 3
    oob_ip_address = 172.16.176.196/24
    oob_default_gateway = 172.16.176.1
    ; apic password is not needed for controllers 2 and 3

It is nice to have a default section that holds default settings so all the required settings are
not needed for each controller.

Wiper only runs against one CIMC at a time though so in order to wipe/provision three APIC's you
would need to run wiper three times and each time provide which CIMC you are running against.  For
example::

    wiper -i sample.ini 172.16.176.191
    wiper -i sample.ini 172.16.176.193
    wiper -i sample.ini 172.16.176.195

