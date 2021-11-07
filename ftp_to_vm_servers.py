#!/usr/bin/env python3.10

"""
This isn't directly relevant to the project per se, but it's been a lot of help in testing it

The project is being tested on a number of Ubuntu Server VMs
This allows me to push changes to the VMs quickly

I'm mainly just adding this to git so I can easily access it from other computers
"""

import json
import paramiko

# Load config file
try:
    with open('.ftp_config.json') as json_file:
        config = json.load(json_file)
except FileNotFoundError:
    print('.ftp_config.json misses')
    exit()


# Connect to each host, then upload/remove files from the respective lists
def ftp(host):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, username=config['username'], password=config['password'], timeout=2)
        sftp = ssh.open_sftp()
        print_string = host

        print_string += ' - put' if config['upload'] else ''
        for file in config['upload']:
            sftp.put(file, f'{config["path"]}{file}')
            print_string += ' ' + file

        print_string += ', remove' if config['remove'] else ''
        for file in config['remove']:
            try:
                sftp.remove(f'{config["path"]}{file}')
                print_string += ' ' + file
            except FileNotFoundError:
                pass

        print(print_string)
        sftp.close()
    except TimeoutError:
        print(host, '- Connection Timeout')


if __name__ == '__main__':
    for server in config['servers']:
        if config['upload'] or config['remove']:
            ftp(server)
