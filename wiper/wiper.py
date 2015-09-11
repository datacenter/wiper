#!/usr/bin/env python

# wiper - the APIC provisioner
#
# Mike Timm - mtimm@cisco.com
#
# Copyright (C) 2015 Cisco Systems Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License

"""
wiper can automatically provision an apic using CLI options or an ini file.

The script utilizes a state machine to attempt to handle all situations that may be encountered
when trying to perform the task of provisioning an APIC.

Requirements:
  pip install paramiko
  pip install git+https://github.com/fgimian/paramiko-expect.git
  pip install git+https://github.com/tyarkoni/transitions.git

There are a very large number of required options if you do not use an ini file to set the options:

  --controller-number
  --strong-passwords
  --infra-vlan-id
  --cimc-ip
  --fabric-name
  --cimc-username
  --controller-name
  --apic-admin-password
  --bd-mc-addresses
  --cimc-password
  --oob-default-gateway
  --int-speed
  --oob-ip-address
  --tep-address-pool
  --number-of-controllers

Use of the ini file is recommended.  You can add DEFAULT options to the ini file using a
default section:

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

To specify a configuration in an ini file for a specific controller, you would use the CIMC ip
address for the section and define controller specific options under it:

  [172.16.176.191]
  cimc_password = ins3965!
  controller_number = 3
  oob_ip_address = 172.16.176.192/24
  oob_default_gateway = 172.16.176.1
  apic_admin_password = ins3965!

Multiple controllers can be added to the ini file.  Options have the following order of precedence
depending how they are defined:

1. options entered via CLI arguments to the script
2. ini file, controller specific section
3. ini file, DEFAULT section

In other words if you define an option in the DEFAULT section of the ini file, it will be overridden
by an option defined in the controller specific section of the ini file and any options defined
by CLI arguments to the script will override the same option set in either the DEFAULT or controller
specific section of the ini file.

If no ini file is provided or if the ini file can not be found, the options must be set via the
CLI arguments to the script.

There is no warning or prompt asking you if you want the script to clear the config on an APIC, this
script just does it.  This may change in the future.
"""

# Standard Library imports
from argparse import ArgumentParser
import ConfigParser
import logging
import re
import socket
import sys
import time
#import telnetlib

# Third party imports
import paramiko
from paramikoe import SSHClientInteraction
from transitions import Machine


class WiperApicInteract(SSHClientInteraction):
    def __init__(self, client, timeout=60, newline='\r', buffer_size=1024,
                 display=False, type=''):
        self.type = type
        SSHClientInteraction.__init__(self, client, timeout, newline, buffer_size,
                 display)


class ProvisionApic(Machine):
    def __init__(self, opts):
        self.cimc = opts['cimc_ip']
        self.cimc_username = opts['cimc_username']
        self.cimc_password = opts['cimc_password']
        self.apic_password = opts['apic_admin_password']
        if opts['verbose'] == "True":
            self.verbose = True
        else:
            self.verbose = False
        if opts['quiet'] == 'True':
            self.quiet = True
        else:
            self.quiet = False
        if opts['simulator'] == True:
            self.simulator = True
        else:
            self.simulator = False
        self.fabric_name = opts['fabric_name']
        self.num_controllers = opts['number_of_controllers']
        self.controller_id = opts['controller_number']
        self.controller_name = opts['controller_name']
        self.tep_address_pool = opts['tep_address_pool']
        self.infra_vlan_id = opts['infra_vlan_id']
        self.bd_mc_address_pool = opts['bd_mc_addresses']
        self.oob_ip_addr = opts['oob_ip_address']
        self.oob_def_gw = opts['oob_default_gateway']
        self.int_speed = opts['int_speed']
        self.strong_passwd = opts['strong_passwords']
        # Used to execute commands in CIMC
        self.cimc_client = None
        # Used to do things on the APIC, has to go through CIMC first of course
        self.apic_client = None
        self.cimc_interact = None
        self.provided_fabric_name = False
        self.states = [
            # Start and initialization states
            {'name': 'start'},
            {'name': 'connect_cimc', 'on_enter': 'on_enter_connect_cimc'},
            # CIMC related states
            {'name': 'check_sol', 'on_enter': 'on_enter_check_sol'},
            {'name': 'configure_sol', 'on_enter': 'on_enter_configure_sol'},
            {'name': 'disconnect_cimc', 'on_enter': 'on_enter_disconnect_cimc'},
            {'name': 'cycle_host', 'on_enter': 'on_enter_cycle_host'},
            # APIC specific initialization states
            {'name': 'connect_apic', 'on_enter': 'on_enter_connect_apic'},
            {'name': 'logout_apic', 'on_enter': 'on_enter_logout_apic'},
            {'name': 'login_apic', 'on_enter': 'on_enter_login_apic'},
            {'name': 'password_login_apic', 'on_enter': 'on_enter_password_login_apic'},
            {'name': 'eraseconfig', 'on_enter': 'on_enter_eraseconfig'},
            # Setup script related states
            {'name': 'press_any_key', 'on_enter': 'on_enter_press_any_key'},
            {'name': 'provide_fabric_name', 'on_enter': 'on_enter_provide_fabric_name'},
            {'name': 'provide_number_ctrlrs', 'on_enter': 'on_enter_provide_number_ctrlrs'},
            {'name': 'provide_ctrlr_id', 'on_enter': 'on_enter_provide_ctrlr_id'},
            {'name': 'provide_ctrlr_name', 'on_enter': 'on_enter_provide_ctrlr_name'},
            {'name': 'provide_tep_addr_pool', 'on_enter': 'on_enter_provide_tep_addr_pool'},
            {'name': 'provide_infra_vlan_id', 'on_enter': 'on_enter_provide_infra_vlan_id'},
            {'name': 'provide_bd_mc_addr_pool', 'on_enter': 'on_enter_provide_bd_mc_addr_pool'},
            {'name': 'provide_oob_address', 'on_enter': 'on_enter_provide_oob_address'},
            {'name': 'provide_oob_def_gw', 'on_enter': 'on_enter_provide_oob_def_gw'},
            {'name': 'provide_int_speed', 'on_enter': 'on_enter_provide_int_speed'},
            {'name': 'provide_strong_passwd', 'on_enter': 'on_enter_provide_strong_passwd'},
            {'name': 'provide_admin_passwd', 'on_enter': 'on_enter_provide_admin_passwd'},
            {'name': 'provide_modify_config', 'on_enter': 'on_enter_provide_modify_config'},
        ]
        Machine.__init__(self, states=self.states, initial='start')

        self.add_transition(trigger='start', source='start', dest='connect_cimc')

        self.add_transition(trigger='cimc_prompt_detected',
                            source='connect_cimc',
                            dest='check_sol')

        self.add_transition(trigger='sol_not_configured',
                            source='check_sol',
                            dest='configure_sol')

        self.add_transition(trigger='sol_config_committed',
                            source='configure_sol',
                            dest='check_sol')

        self.add_transition(trigger='cycle_host',
                            source='connect_apic',
                            dest='cycle_host')

        # We can enter the connect_apic state from multiple sources, this states
        # entry callback will need to be smarter than the average bear.
        self.add_transition(trigger='connect_to_apic',
                            source=['check_sol', 'logout_apic'],
                            dest='connect_apic')

        self.add_transition(trigger='apic_prompt_detected',
                            source='connect_apic',
                            dest='logout_apic')

        self.add_transition(trigger='apic_login_detected',
                            source=['connect_apic', 'logout_apic', 'password_login_apic',
                                    'cycle_host'],
                            dest='login_apic')

        self.add_transition(trigger='apic_password_detected',
                            source=['connect_apic', 'cycle_host'],
                            dest='password_login_apic')

        self.add_transition(trigger='apic_prompt_detected',
                            source=['login_apic', 'cycle_host'],
                            dest='eraseconfig')

        self.add_transition(trigger='press_any_key',
                            source=['connect_apic', 'eraseconfig', 'cycle_host'],
                            dest='press_any_key')

        # This transition can happen from connect_apic or provide_modify_config
        self.add_transition(trigger='enter_fabric_name',
                            source=['connect_apic', 'provide_modify_config', 'press_any_key'],
                            dest='provide_fabric_name')

        self.add_transition(trigger='enter_num_ctrlrs',
                            source=['connect_apic', 'provide_fabric_name'],
                            dest='provide_number_ctrlrs')

        self.add_transition(trigger='enter_ctrlr_id',
                            source=['connect_apic', 'provide_number_ctrlrs'],
                            dest='provide_ctrlr_id')

        self.add_transition(trigger='enter_ctrlr_name',
                            source=['connect_apic', 'provide_ctrlr_id'],
                            dest='provide_ctrlr_name')

        self.add_transition(trigger='enter_tep_addr_pool',
                            source=['connect_apic', 'provide_ctrlr_name'],
                            dest='provide_tep_addr_pool')

        self.add_transition(trigger='enter_infra_vlan_id',
                            source=['connect_apic', 'provide_tep_addr_pool'],
                            dest='provide_infra_vlan_id')

        self.add_transition(trigger='enter_bd_mc_addr_pool',
                            source=['connect_apic', 'provide_infra_vlan_id'],
                            dest='provide_bd_mc_addr_pool')

        self.add_transition(trigger='enter_oob_ip_addr',
                            source=['connect_apic',
                                    'provide_bd_mc_addr_pool',
                                    'provide_infra_vlan_id'],
                            dest='provide_oob_address')

        self.add_transition(trigger='enter_oob_def_gw',
                            source=['connect_apic', 'provide_oob_address'],
                            dest='provide_oob_def_gw')

        self.add_transition(trigger='enter_int_speed',
                            source=['connect_apic', 'provide_oob_def_gw'],
                            dest='provide_int_speed')

        self.add_transition(trigger='enter_strong_passwd',
                            source=['connect_apic', 'provide_int_speed'],
                            dest='provide_strong_passwd')

        self.add_transition(trigger='enter_admin_passwd',
                            source=['connect_apic', 'provide_strong_passwd'],
                            dest='provide_admin_passwd')

        self.add_transition(trigger='reenter_admin_passwd',
                            source=['connect_apic', 'provide_admin_passwd'],
                            dest='provide_admin_passwd')

        self.add_transition(trigger='enter_edit_cfg',
                            source=['connect_apic', 'provide_admin_passwd', 'provide_int_speed'],
                            dest='provide_modify_config')

        self.add_transition(trigger='restart_setup',
                            source='provide_modify_config',
                            dest='provide_fabric_name')

    def on_enter_connect_cimc(self):
        prompt = r'.*C220.*# '
        self.cimc_client = paramiko.SSHClient()
        self.apic_client = paramiko.SSHClient()
        self.cimc_client.load_system_host_keys()
        self.apic_client.load_system_host_keys()
        self.cimc_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.apic_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            self.log("Connecting to {0} as user {1} for CIMC control.".format(self.cimc,
                                                                              self.cimc_username),
                     print_only=True)
            # TODO: put these in different threads to speed up connecting
            self.cimc_client.connect(hostname=self.cimc, username=self.cimc_username,
                                     password=self.cimc_password, look_for_keys=False)
            self.log("Connecting to {0} as user {1} for APIC control.".format(self.cimc,
                                                                              self.cimc_username),
                     print_only=True)
            self.apic_client.connect(hostname=self.cimc, username=self.cimc_username,
                                     password=self.cimc_password, look_for_keys=False)
        except paramiko.ssh_exception.PasswordRequiredException, err:
            print("Unable to connect to CIMC - Password is required because: {0}".format(err))
            sys.exit(-1)

        self.cimc_interact = WiperApicInteract(self.cimc_client, timeout=10, display=self.verbose,
                                           type='cimc')
        self.cimc_interact.send('\n')

        self.apic_interact = WiperApicInteract(self.apic_client, timeout=10, display=self.verbose,
                                           type='apic')
        self.apic_interact.send('\n')

        try:
            self.cimc_interact.expect(prompt)
            self.clear_interact_output(self.cimc_interact)
            self.apic_interact.expect(prompt)
            self.clear_interact_output(self.apic_interact)

        except:
            print("Failed to detect CIMC prompt using '{0}'".format(prompt))
            raise

    def on_enter_check_sol(self):
        prompt = r'.*C220.*# '
        self.log("Ensuring Serial Over LAN is configured properly.", print_only=True)
        while True:
            self.do_cmd('show sol', prompt, self.cimc_interact)
            try:
                sol_list = re.split(r'\s*', self.cimc_interact.current_output_clean.split('\n')[2])
                sol_enabled, sol_baud, sol_com = sol_list[0], sol_list[1], sol_list[2]
                if 'yes' not in sol_enabled or '115200' not in sol_baud or 'com0' not in sol_com:
                    self.log("Could not configure sol properly, trying again in 3 seconds")
                    time.sleep(3)
                    self.log("Serial Over LAN is not configured, moving to configure it.",
                             print_only=True)
                    self.sol_not_configured()
                else:
                    self.log("Serial Over LAN is configured.", print_only=True)
                    return
            except (KeyError, IndexError):
                self.log("The command output for 'show sol' was not valid, trying again.",
                         print_only=True)

    def on_enter_configure_sol(self):
        sol_prompt = r'C220-.* /sol # '
        sol_needs_commit_prompt = r'C220-.* /sol \*# '
        top_prompt = r'C220-.*# '
        cmds = list()
        cmds.append(('scope sol', sol_prompt, True, 10))
        cmds.append(('set baud-rate 115200', sol_needs_commit_prompt, True, 10))
        cmds.append(('set comport com0', sol_needs_commit_prompt, True, 10))
        cmds.append(('set enabled yes', sol_needs_commit_prompt, True, 10))
        cmds.append(('commit', sol_prompt, True, 30))
        cmds.append(('top', top_prompt, True, 10))
        self.do_cmds(cmds, self.cimc_interact)
        self.log("Serial Over LAN is configured.", print_only=True)
        self.sol_config_committed()

    def on_enter_connect_apic(self):
        # When we see one of these regex's we transition to the specified state.
        transitions = {
            r'.*login:.*': self.apic_login_detected,
            r'.*Password:.*': self.apic_password_detected,
            r'.*:~> ': self.apic_prompt_detected,
            r'.*Press any key to continue....*': self.press_any_key,
            r'.*Enter the fabric name \[.*\]:.*': self.enter_fabric_name,
            r'.*Enter the number of controllers in the fabric \(1-9\) \[[0-9]+]:.*':
                self.enter_num_ctrlrs,
            r'.*Enter the controller ID \(1-3\) \[[0-9]+\]:.*': self.enter_ctrlr_id,
            r'.*Enter the controller name \[.*\]:.*': self.enter_ctrlr_name,
            r'.*Enter address pool for TEP addresses \[.*\]:.*': self.enter_tep_addr_pool,
            r'.*Enter the VLAN ID for infra network \(1-4094\).*:.*': self.enter_infra_vlan_id,
            r'.*Enter address pool for BD multicast addresses \(GIPO\) \[.*\]:.*':
                self.enter_bd_mc_addr_pool,
            r'.*Enter the IP address \[.*\].*': self.enter_oob_ip_addr,
            r'.*Enter the IP address of the default gateway \[.*\]:.*': self.enter_oob_def_gw,
            r'.*Enter the interface speed/duplex mode \[.*\]:.*': self.enter_int_speed,
            r'.*Enable strong passwords\? \[.*\]:.*': self.enter_strong_passwd,
            r'.*Enter the password for admin:.*': self.enter_admin_passwd,
            r'.*Reenter the password for admin:.*': self.reenter_admin_passwd,
            r'.*Would you like to edit the configuration\? \(y/n\) \[.*\].*': self.enter_edit_cfg,
        }
        # connect to the APIC console and send a newline
        try:
            self.log("Trying to connect to the APIC console via Serial Over LAN, " +
                     "using a timeout of 10 seconds.", print_only=True)
            index = self.do_cmd("connect host\n", transitions.keys(), self.apic_interact,
                                clear_outputs=True)
        except socket.timeout:
            # Unable to connect to CIMC, try to power cycle the host
            self.log("No prompt seen from the APIC, will try to power cycle the host.")
            self.cycle_host()
            return
        # Transition to the state needed by the prompt we get back.
        transitions[transitions.keys()[index]]()

    def on_enter_cycle_host(self):
        # If you connect to the APIC via KVM and start the initial setup script, the console (ttyS0)
        # is no longer connected/updating.  So we have to cycle the host to recover.
        chassis_prompt = r'C220-.* /chassis # '
        power_cycle_prompt = r'.*Do you want to continue\?\[.*\].*'
        top_prompt = r'C220-.*# '
        cmds = list()
        cmds.append(('scope chassis', chassis_prompt, True, 10))
        cmds.append(('power cycle', power_cycle_prompt, True, 10))
        cmds.append(('y', chassis_prompt, True, 10))
        cmds.append(('top', top_prompt, True, 10))
        self.log("Sending APIC power cycle commands to CIMC.", print_only=True)
        self.do_cmds(cmds, self.cimc_interact)
        # hopefully we would only end up at press any key, not sure how we end up in the others
        # after no response from the APIC.
        transitions = {
            r'.*login:.*': self.apic_login_detected,
            r'.*Password:.*': self.apic_password_detected,
            r'.*:~> ': self.apic_prompt_detected,
            r'.*Press any key to continue....*': self.press_any_key,
        }
        self.log("Waiting on a power cycle for up to 600 seconds.", print_only=True)
        try:
            index = self.apic_interact.expect(transitions.keys(), timeout=600)
        except socket.timeout:
            print "Unable to get a response from the controller after a power cycle."
            print "Please verify that the controller software is installed correctly"
            print "and that the controller boots up fine."
            raise
        transitions[transitions.keys()[index]]()

    def on_enter_disconnect_cimc(self):
        self.log("Disconnecting from both CIMC and the APIC by closing the connections.",
                 print_only=True)
        self.cimc_client.close()
        self.apic_client.close()
        self.cimc_client = self.apic_client = None

    def on_enter_logout_apic(self):
        prompt = r'.*login:.*'
        self.log("Found a CLI prompt on the APIC, logging out.", print_only=True)
        self.do_cmd("exit", prompt, self.apic_interact)
        self.apic_login_detected()

    def on_enter_login_apic(self):
        prompts = [
            r'.*Password:.*',
            r'.*~> .*',
        ]
        self.log("Found a login prompt on the APIC, logging in as 'rescue-user'.", print_only=True)
        index = self.do_cmd('rescue-user', prompts, self.apic_interact)
        if index == 0:
            # Typically this would be APIC1
            prompt = r'.*~> .*'
            self.log("Rescue-user was prompted for a password, sending the APIC admin password.",
                     print_only=True)
            # We need some extra time here because we may have just booted.
            self.do_cmd(self.apic_password, prompt, self.apic_interact, timeout=60)
            self.apic_prompt_detected()
        elif index == 1:
            self.log("Found a CLI prompt on the apic.", print_only=True)
            self.apic_prompt_detected()
        else:
            raise ValueError("Index was invalid, this should never happen")

    def on_enter_password_login_apic(self):
        prompt = r'.*login:.*'
        self.log("Login was already started, sending ctrl-d to start over.", print_only=True)
        # Send a control-d (EOF) to start the login process over.
        self.do_cmd(chr(4), prompt, self.apic_interact)
        self.apic_login_detected()

    def on_enter_eraseconfig(self):
        prompt = (r'.*Do you want to cleanup the initial setup data\? The system will be ' +
                  r'REBOOTED. \(Y/n\):.*')
        self.log("Sending 'eraseconfig setup' command to the APIC", print_only=True)
        self.do_cmd('eraseconfig setup', prompt, self.apic_interact)
        prompt = r'.*Press any key to continue....*'
        self.log("Sending 'Y' to continue with the eraseconfig setup, will wait for the reboot, " +
                 "timeout is 600 seconds.", print_only=True)
        self.do_cmd('Y', prompt, self.apic_interact, timeout=600)
        self.press_any_key()

    def on_enter_press_any_key(self):
        prompt = r'.*Enter the fabric name \[.*\]:.*'
        self.log("Starting the setup script on the APIC.", print_only=True)
        # May need to wrap this in a try/except for socket.timeout if someone is able to catch
        # steal the I/O on KVM before we get started, seems like a very unlikely thing to have
        # happen though
        self.do_cmd("", prompt, self.apic_interact)
        self.enter_fabric_name()

    def on_enter_provide_fabric_name(self):
        prompt = r'.*Enter the number of controllers in the fabric \(1-9\) \[[0-9]+]:.*'
        self.log("Setting the fabric name to '{0}' on the APIC.".format(self.fabric_name),
                 print_only=True)
        self.do_cmd(self.fabric_name, prompt, self.apic_interact)
        self.provided_fabric_name = True
        self.enter_num_ctrlrs()

    def on_enter_provide_number_ctrlrs(self):
        prompt = r'.*Enter the controller ID \(1-3\) \[[0-9]+\]:.*'
        self.log("Setting number of controllers to '{0}' on the APIC.".format(self.num_controllers),
                 print_only=True)
        self.do_cmd(self.num_controllers, prompt, self.apic_interact)
        self.enter_ctrlr_id()

    def on_enter_provide_ctrlr_id(self):
        prompt = r'.*Enter the controller name \[.*\]:.*'
        self.log("Setting the controller id to '{0}' on the APIC.".format(self.controller_id),
                 print_only=True)
        self.do_cmd(self.controller_id, prompt, self.apic_interact)
        self.enter_ctrlr_name()

    def on_enter_provide_ctrlr_name(self):
        prompt = r'.*Enter address pool for TEP addresses \[.*\]:.*'
        self.log("Setting the controller name to '{0}' on the APIC.".format(self.controller_name),
                 print_only=True)
        self.do_cmd(self.controller_name, prompt, self.apic_interact)
        self.enter_tep_addr_pool()

    def on_enter_provide_tep_addr_pool(self):
        prompt = r'.*Enter the VLAN ID for infra network \(1-4094\).*:.*'
        self.log("Setting the TEP Address Pool to '{0}' on the APIC.".format(self.tep_address_pool),
                 print_only=True)
        self.do_cmd(self.tep_address_pool, prompt, self.apic_interact)
        self.enter_infra_vlan_id()

    def on_enter_provide_infra_vlan_id(self):
        # APICs other than APIC1 go to a different prompt.
        prompts = [
            r'.*Enter address pool for BD multicast addresses \(GIPO\) \[.*\]:.*',
            r'.*Enter the IP address \[.*\].*',
        ]
        self.log("Setting the infra VLAN ID to '{0}' on the APIC.".format(self.infra_vlan_id),
                 print_only=True)
        index = self.do_cmd(self.infra_vlan_id, prompts, self.apic_interact)
        if index == 0:
            self.enter_bd_mc_addr_pool()
        elif index == 1:
            self.enter_oob_ip_addr()

    def on_enter_provide_bd_mc_addr_pool(self):
        prompt = r'.*Enter the IP address \[.*\].*'
        self.log("Setting the BD Multicast Address Pool to '{0}' on the APIC".format(
            self.bd_mc_address_pool),
                 print_only=True)
        self.do_cmd(self.bd_mc_address_pool, prompt, self.apic_interact)
        self.enter_oob_ip_addr()

    def on_enter_provide_oob_address(self):
        prompt = r'.*Enter the IP address of the default gateway \[.*\]:.*'
        self.log("Setting the Out Of Band IP address to {0} on the APIC.".format(self.oob_ip_addr),
                 print_only=True)
        self.do_cmd(self.oob_ip_addr, prompt, self.apic_interact)
        self.enter_oob_def_gw()

    def on_enter_provide_oob_def_gw(self):
        prompt = r'.*Enter the interface speed/duplex mode \[.*\]:.*'
        self.log("Setting the Out Of Band default gateway to {0} ".format(self.oob_def_gw) +
                 "on the APIC", print_only=True)
        self.do_cmd(self.oob_def_gw, prompt, self.apic_interact)
        self.enter_int_speed()

    def on_enter_provide_int_speed(self):
        prompts = [
            r'.*Enable strong passwords\? \[.*\]:.*',
            r'.*Would you like to edit the configuration\? \(y/n\) \[.*\].*',
        ]
        self.log("Setting the Out Of Band interface speed/duplex to {0} ".format(self.int_speed) +
                 "on the APIC.", print_only=True)
        index = self.do_cmd(self.int_speed, prompts, self.apic_interact)
        if index == 0:
            # We are on APIC1
            self.enter_strong_passwd()
        elif index == 1:
            # We are not on APIC1
            self.enter_edit_cfg()
        else:
            # Should never happen
            raise ValueError("Index can not be {0}".format(index) + " here.")

    def on_enter_provide_strong_passwd(self):
        prompt = r'.*Enter the password for admin:.*'
        self.log("Sending '{0}' for enabling strong passwords ".format(self.strong_passwd) +
                 "on the APIC", print_only=True)
        self.do_cmd(self.strong_passwd, prompt, self.apic_interact)
        self.enter_admin_passwd()

    def on_enter_provide_admin_passwd(self):
        prompts = [
            r'.*Reenter the password for admin:.*',
            r'.*Would you like to edit the configuration\? \(y/n\) \[.*\].*',
        ]
        self.log("Setting the admin password on the APIC.", print_only=True)
        index = self.do_cmd(self.apic_password, prompts, self.apic_interact)
        if index == 0:
            prompt = r'.*Would you like to edit the configuration\? \(y/n\) \[.*\].*'
            self.log("Resending the admin password to the APIC.", print_only=True)
            self.do_cmd(self.apic_password, prompt, self.apic_interact)
        self.enter_edit_cfg()

    def on_enter_provide_modify_config(self):
        if self.provided_fabric_name:
            self.log("Completed a full setup script attempt, waiting for the APIC login prompt " +
                     "for up to 60 seconds.", print_only=True)
            self.do_cmd('n', r'.*login:.*', self.apic_interact, timeout=60)
        else:
            prompt = r'.*Enter the fabric name \[.*\]:.*'
            self.log("Setting the fabric name to '{0}' on the APIC.".format(self.fabric_name),
                 print_only=True)
            self.do_cmd('y', prompt, self.apic_interact)
            self.enter_fabric_name()

    def do_cmds(self, cmd_list, interact, clear_outputs=True):
        """ Do multiple commands in a row

        Each command needs to have its prompt defined.  This does not allow
        identification of which prompt matched.

        Args:
            cmd_list (list of tuples):  A list of tuples in the form:

                (cmd, prompt)

            cmd is a string and prompt could be a string or a list of strings.
        """
        self.log("Sending a bulk set of commands to {0}".format(interact.type))
        for cmd_prompt in cmd_list:
            if len(cmd_prompt) == 2:
                self.do_cmd(cmd_prompt[0], cmd_prompt[1], interact,
                            clear_outputs=clear_outputs)
            elif len(cmd_prompt) == 3:
                self.do_cmd(cmd_prompt[0], cmd_prompt[1], interact,
                            clear_outputs=cmd_prompt[2])
            elif len(cmd_prompt) == 4:
                self.do_cmd(cmd_prompt[0], cmd_prompt[1], interact,
                            clear_outputs=cmd_prompt[2], timeout=cmd_prompt[3])
            else:
                raise ValueError("Invalid command tuple do_cmds {0}".format(
                    cmd_prompt))

    def do_cmd(self, cmd, prompt, interact, clear_outputs=True, timeout=10):
        """ Do a command and expect a prompt.

        Args:
            cmd (str): the command to run
            prompt (str or list): the prompt to expect

        Raises:
            Exception: Could raise an exception on send or expect.

        Returns:
            int: The index in the prompts list that matched.
        """
        if not interact:
            raise RuntimeError("Paramiko-expect interact not initialized yet")
        if clear_outputs is True:
            self.clear_interact_output(interact)
        try:
            self.log("Sending cmd: '{0}'".format(cmd), debug_only=True)
            interact.send(str(cmd))
        except:
            print("Failed to send the command: '{0}'".format(cmd))
            raise
        try:
            self.log("Expecting prompt: '{0}' with a timeout of {1} seconds".format(prompt,
                                                                                    timeout),
                     debug_only=True)
            return interact.expect(prompt, timeout=timeout)
        except socket.timeout:
            print("Failed to detect the prompt using: '{0}'".format(prompt))
            print("current_output: {0}".format(interact.current_output))
            raise

    def clear_interact_output(self, interact):
        if not interact:
            raise RuntimeError("Paramiko-expect interact not initialized yet")
        self.log("Clearing interact output for - {0}".format(interact.type), debug_only=True)
        interact.current_output = ''
        interact.current_output_clean = ''


    def log(self, message, debug_only=False, print_only=False):
        if not self.quiet and not debug_only:
            print(message)
        if self.verbose and not print_only:
            logging.info(message)

def parse_ini(option_names, opts):
    parser = ConfigParser.SafeConfigParser()
    found_ini_file = parser.read([opts['ini_file']])

    if not found_ini_file:
        return None

    # CIMC IP address is used to load in the config for the specific controller
    # if the config option does not exist for that controller, it falls back to the DEFAULT section
    cimc_ip = opts['cimc_ip']

    new_opts = {}
    for name in option_names:
        try:
            new_opts[name] = parser.get(cimc_ip, name, vars=opts)
        except ConfigParser.NoSectionError:
            return opts
    return new_opts


def parse_args():
    parser = ArgumentParser('Provision APICs via CIMC Serial Over LAN')

    parser.add_argument('-ap', '--apic_admin_password', required=False, default=None,
                        help='The APIC admin user password to enter into the APIC setup script.')

    parser.add_argument('-b', '--bd-mc-addresses', required=False, default=None,
                        help='The Bridge Domain Multicast address range to enter into the APIC ' +
                             'setup script.')

    parser.add_argument('cimc_ip', help='CIMC hostname or IP address used to ssh to CIMC')

    parser.add_argument('-cna', '--controller-name', required=False, default=None,
                        help='The controller name to enter into the APIC setup script.')

    parser.add_argument('-cnu', '--controller_number', required=False, type=str, default=None,
                        help='The controller number (id) to enter into the APIC setup script.')

    parser.add_argument('-cp', '--cimc_password', required=False, default=None,
                        help='CIMC password')

    parser.add_argument('-cu', '--cimc_username', required=False, default=None,
                        help='CIMC username')

    parser.add_argument('-i', '--ini-file', required=False, default='wiper.ini',
                        help='Use an ini file to find parameters to provision an APIC.')

    parser.add_argument('-is', '--int-speed', required=False, default=None,
                        choices=[
                            'auto',
                            '10baseT/Half',
                            '10baseT/Full',
                            '100baseT/Half',
                            '100baseT/Full',
                            '1000baseT/Full'
                        ])

    parser.add_argument('-iv', '--infra-vlan-id', required=False, default=None,
                        help='The infra vlan id to enter into the APIC setup script.')

    parser.add_argument('-f', '--fabric-name', required=False, default=None,
                        help='The fabric name to enter into the APIC setup script.')

    #parser.add_argument('-g', '--generate-ini', required=False, default="False",
    #                    action="store_const", const="True",
    #                    help='Generate an ini file with default settings for a specific controller')

    parser.add_argument('-nc', '--number-of-controllers', required=False, type=str, default=None,
                        help='The number of controllers to enter into the APIC setup script.')

    parser.add_argument('-od', '--oob-default-gateway', required=False, default=None,
                        help='The APIC Out-Of-Band default gateway to enter into the APIC setup ' +
                             'script.')

    parser.add_argument('-oi', '--oob-ip-address', required=False, default=None,
                        help='The APIC Out-Of-Band IP address to enter into the APIC setup script.')

    parser.add_argument('-q', '--quiet', required=False, default='False', action='store_const',
                        const='True',
                        help='Be quiet, do not provide status messages')

    parser.add_argument('-sim', '--simulator', required=False, action="store_const", const='True',
                        default='False',
                        help='This flag identifies the APIC as a simulator.')

    parser.add_argument('-sp', '--strong-passwords', required=False, default=None,
                        choices=['Y', 'n'],
                        help='Strong password option to enter into the APIC setup script.')

    parser.add_argument('-t', '--tep-address-pool', required=False, default=None,
                        help='The TEP address pool to enter into the APIC setup script.')

    parser.add_argument('-v', '--verbose', required=False, default='False', action='store_const',
                        const='True',
                        help='Enable debugging and be verbose.')

    args = parser.parse_args()

    if args.verbose == 'True':
        logging.basicConfig(level=logging.INFO)

    option_names = args.__dict__.keys()
    opts = {}
    # Remove any CLI args that were set to None
    for option in option_names:
        if args.__dict__[option] is not None:
            opts[option] = args.__dict__[option]

    # Parse an ini file if it exists, pass in the opts to override any options in that ini file.
    combined_options = parse_ini(option_names, opts)

    if combined_options is not None:
        opts = combined_options

    # Ensure we have the required options, otherwise exit
    required_options = [
        'controller_number',
        'strong_passwords',
        'infra_vlan_id',
        'cimc_ip',
        'fabric_name',
        'cimc_username',
        'controller_name',
        'apic_admin_password',
        'bd_mc_addresses',
        'cimc_password',
        'oob_default_gateway',
        'int_speed',
        'oob_ip_address',
        'tep_address_pool',
        'number_of_controllers'
    ]
    for option_name in required_options:
        try:
            opts[option_name]
        except KeyError:
            print("Unable to complete provisioning.  Missing --{0} option".format(
                option_name.replace('_', '-')))
            print("")
            print("These options are all required:")
            for option in required_options:
                print("  --{0}".format(option.replace('_', '-')))
            print("")
            print("These can also be set via an ini file.")
            sys.exit(-1)
    return opts


def main():
    options = parse_args()
    pa = ProvisionApic(opts=options)

    # The start transition automatically moves the state to connect_cimc
    pa.start()
    # Once connected to CIMC, use the cimc_prompt_detected transition to move
    # to the check_sol state, when this returns, we know we can connect to the
    # apic over serial over LAN.
    pa.cimc_prompt_detected()
    # SOL is configured, so move the state to connect_apic via the connect_to_apic transition
    # this is the heart of the provisioning process.  When this returns, the APIC
    # should be provisioned.
    pa.connect_to_apic()

    # If we get here and still have a client, disconnect from it and set it to None (just in case)
    if pa.client is not None:
        pa.to_disconnect_cimc()
        pa.client = None


if __name__ == '__main__':
    main()
