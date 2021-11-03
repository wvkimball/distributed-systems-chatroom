#!/usr/bin/env python3.10

import socket
import threading
import utility
from time import sleep, time

# Create a UDP socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Find the server's ip and set the port
server_ip = utility.get_ip()
server_port = 10001
server_address = (server_ip, server_port)

# Buffer size
buffer_size = utility.buffer_size

# Sets are used here to prevent duplicates
clients = set()  # Set of clients
servers = set()  # Set of clients

# Variables to store the leader server
is_leader = False
leader_address = ''
last_leader_heartbeat = time()


def main():
    server_socket.bind((server_ip, server_port))
    seek_other_servers()
    print('Server up and running at {}'.format(server_ip))

    threading.Thread(target=broadcast_listener).start()
    threading.Thread(target=manage_chat).start()
    threading.Thread(target=heartbeat).start()


# Runs on startup, trys to find other servers to join
def seek_other_servers():
    broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    broadcast_socket.bind((server_ip, 0))
    broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # this is a broadcast socket
    broadcast_socket.settimeout(1)

    got_response = False

    # 5 attempts are made to find another server / other servers
    # After this, the server assumes it is the only one and considers itself leader
    for i in range(0, 5):
        broadcast_socket.sendto(utility.broadcast_code.encode(), ('<broadcast>', utility.broadcast_port))
        print("Looking for other servers")

        # Wait for a response packet. If no packet has been received in 2 seconds, sleep then broadcast again
        try:
            data, address = broadcast_socket.recvfrom(1024)
            if data.startswith((utility.response_code + server_ip).encode()):
                print("Found server at", address[0])
                send_message('#*#SERV', address)
                got_response = True
                set_leader(address)
                break
        except TimeoutError:
            pass

    broadcast_socket.close()
    if not got_response:
        set_leader(server_address)
        print('No other servers found')


# Set the lead server. If the leader address is our address, than is_leader is true
def set_leader(address):
    global is_leader, leader_address
    is_leader = address == server_address
    leader_address = address


# Function to listen for broadcasts from clients and respond when a broadcast is heard
def broadcast_listener():
    listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    listener_socket.bind(('', utility.broadcast_port))

    while True:
        data, address = listener_socket.recvfrom(1024)  # wait for a packet
        if data.startswith(utility.broadcast_code.encode()):
            print("Received broadcast from", address[0])
            send_message(utility.response_code + address[0], address)


# Function that receives a message and either distributes it to the clients or handles it as a command
# TODO: add good receipt confirmations and maybe idempotency
def manage_chat():
    while True:
        data, address = server_socket.recvfrom(buffer_size)
        message = data.decode()
        # print('Received message {} from address {}'.format(message, address))

        if message[0:3] == '#*#':
            server_command(message[3:], address)
        else:
            distribute_to_clients(message, address)


# TODO: This is bad and I feel bad for having written it. I'll rewrite this soon
# Handles commands sent to the server
# Pattern matching is awesome, and it's worth updating python just to have it
def server_command(command, address):
    match command.split('#*#'):
        case ['JOIN', add_client_ip, add_client_port]:
            pass  # To be used when I rewrite this method
        case ['JOIN']:  # Request from a client to join the server's chatroom
            add_client(address)
        case ['EXIT']:  # Request from a client to be removed from the chatroom
            clients.remove(address)
            send_message('#*#EXIT', address)
            distribute_to_clients('{} has left the chat'.format(address[0]), address, True)
            distribute_to_servers('#*#REMOVE-CLIENT#*#{}#*#{}'.format(address[0], address[1]))
        case ['SERV', add_server_ip, add_server_port]:
            pass  # To be used when I rewrite this method
        case ['SERV']:  # Request from a server to be added to the server pool
            add_server(address)
        case ['ADD-CLIENT', add_client_ip, add_client_port]:  # Command from the leader to add a client
            client_to_add = (add_client_ip, int(add_client_port))
            if client_to_add not in clients:  # Not in is maybe needless with sets, but it prevents the extra print
                clients.add(client_to_add)
                print('Command from {}, {} added to clients'.format(address, client_to_add))
        case ['ADD-SERVER', add_server_ip, add_server_port]:  # Command from the leader to add a server
            server_to_add = (add_server_ip, int(add_server_port))
            if server_to_add != server_address and server_to_add not in servers:
                servers.add(server_to_add)
                print('Command from {}, {} added to servers'.format(address, server_to_add))
        case ['REMOVE-CLIENT', re_client_ip, re_client_port]:  # Command from the leader to remove a client
            client_to_remove = (re_client_ip, int(re_client_port))
            try:
                clients.remove(client_to_remove)
                print('Command from {}, {} removed from clients'.format(address, client_to_remove))
            except KeyError:  # If the leader commanded us to remove a server we don't know, then request an update
                print('Command from {} to remove unknown client {}'.format(address, client_to_remove))
                print('Requesting update')
                send_message('#*#REQUEST-UPDATE', address)
        case ['REQUEST-UPDATE']:  # If I'm the leader, update all servers with what we know
            if is_leader:
                update_servers()
        case ['CLEAR']:  # Clear our clients and servers. This should only be done before an update
            print('!!! clients and servers have been cleared !!!')
            clients.clear()
            servers.clear()
        case ['HEARTBEAT']:  # If the leader is getting heartbeats something is wrong
            if is_leader or address != leader_address:
                distribute_to_servers('#*#REQUEST-UPDATE')
            else:
                update_last_leader_heartbeat()
        case ['LEADER']:
            if address != leader_address:
                set_leader(address)
                print(address, 'has declared itself leader')
                update_last_leader_heartbeat()


# Adds a client to our list and tells the other servers about it
# If not the leader, request an update
def add_client(address):
    clients.add(address)
    print('{} added to clients'.format(address))
    distribute_to_servers('#*#ADD-CLIENT#*#{}#*#{}'.format(address[0], address[1]))
    if is_leader:
        send_message('Welcome to the chat!', address)
        distribute_to_clients('{} has joined the chat'.format(address[0]), address, True)
    else:
        distribute_to_servers('#*#REQUEST-UPDATE')


# Adds a server to our list and updates servers, so that the new server has everything
def add_server(address):
    servers.add(address)
    print('{} added to servers'.format(address))
    update_servers()


# Sends information on all clients and servers to all servers
def update_servers():
    print('Updating clients/servers')
    distribute_to_clients('#*#SERV', server_message=True)
    for client in clients:
        distribute_to_servers('#*#ADD-CLIENT#*#{}#*#{}'.format(client[0], client[1]), False)
    distribute_to_servers('#*#ADD-SERVER#*#{}#*#{}'.format(server_ip, server_port), False)
    for server in servers:
        distribute_to_servers('#*#LEADER'.format(server[0], server[1]), False)
        distribute_to_servers('#*#ADD-SERVER#*#{}#*#{}'.format(server[0], server[1]), False)


# Loops through all clients and sends them the message
# If a sender is provided, they are not sent the message
def distribute_to_clients(message, sender='', server_message=False):
    for client in clients:
        if client != sender:
            ident = ''
            if not server_message:
                ident = '{}: '.format(sender[0])
            send_message(ident + message, client)


# Loops through all other servers and sends them the message/command
def distribute_to_servers(message, print_message=True):
    for server in servers:
        send_message(message, server, print_message)


# Sends a message to an address/client
def send_message(message, address, print_message=True):
    server_socket.sendto(str.encode(message), address)
    if print_message:
        print('Send message {} to address {}'.format(message, address))


def heartbeat():
    while True:
        if is_leader:
            distribute_to_servers('#*#HEARTBEAT', False)
            sleep(1)
        else:
            if time() - last_leader_heartbeat >= 5:
                print('Last leader heartbeat is more than 5 seconds ago')
                next_leader()
                update_last_leader_heartbeat()  # Give the new leader a chance to start sending heartbeats
            sleep(1)


def update_last_leader_heartbeat():
    global last_leader_heartbeat
    last_leader_heartbeat = time()


# TODO: replace with a proper leader election algorithm
def next_leader():
    servers.remove(leader_address)
    set_leader(min({server_address}.union(servers)))
    print('The new leader should be', leader_address)
    if is_leader:
        distribute_to_servers('#*#LEADER')
        distribute_to_clients('#*#SERV', server_message=True)


if __name__ == '__main__':
    main()
