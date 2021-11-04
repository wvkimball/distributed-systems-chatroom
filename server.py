#!/usr/bin/env python3.10

import socket
import threading
from utility import BUFFER_SIZE
import utility
from time import sleep

# Constants
# Server connection data
SERVER_IP = utility.get_ip()

# Create TCP socket for listening
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((SERVER_IP, 0))
server_socket.listen()

# Find listening port and save server address tuple
server_port = server_socket.getsockname()[1]
server_address = (SERVER_IP, server_port)

# Lists for connected clients and servers
clients = []
servers = [server_address]  # Server list starts with this server in it

# Variables for leadership and voting
leader = None
is_leader = False
is_voting = False
neighbor = None


def main():
    utility.cls()
    startup_broadcast()

    threading.Thread(target=broadcast_listener).start()
    threading.Thread(target=manage_chat).start()
    threading.Thread(target=heartbeat).start()


# Broadcasts looking for another active server
def startup_broadcast():
    broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    broadcast_socket.bind((SERVER_IP, 0))
    broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # this is a broadcast socket
    broadcast_socket.settimeout(1)

    got_response = False

    # 5 attempts are made to find another server
    # After this, the server assumes it is the only one and considers itself leader
    for i in range(0, 5):
        broadcast_socket.sendto(utility.BROADCAST_CODE.encode(), ('<broadcast>', utility.BROADCAST_PORT))
        print("Looking for other servers")

        # Wait for a response packet. If no packet has been received in 2 seconds, sleep then broadcast again
        try:
            data, address = broadcast_socket.recvfrom(1024)
            if data.startswith(f'{utility.RESPONSE_CODE}_{SERVER_IP}'.encode()):
                print("Found server at", address[0])
                response_port = int(data.decode().split('_')[2])
                utility.tcp_transmit_message(f'#JOIN_server_1_{SERVER_IP}_{server_port}',
                                             (address[0], response_port))
                got_response = True
                set_leader((address[0], response_port))
                break
        except TimeoutError:
            pass

    broadcast_socket.close()
    if not got_response:
        print('No other servers found')
        set_leader(server_address)


# Function to listen for broadcasts from clients/servers and respond when a broadcast is heard
# Only the leader responds to broadcasts
def broadcast_listener():
    print('Server up and running at {}'.format(server_address))

    listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    listener_socket.bind(('', utility.BROADCAST_PORT))

    while True:
        data, address = listener_socket.recvfrom(BUFFER_SIZE)  # wait for a packet
        if is_leader and data.startswith(utility.BROADCAST_CODE.encode()):
            print("Received broadcast from", address[0])
            # Respond with the response code, the IP we're responding to, and the the port we're listening with
            listener_socket.sendto(str.encode(f'{utility.RESPONSE_CODE}_{address[0]}_{server_port}'), address)


# Function to manage the chat
# passes valid commands to server_command
def manage_chat():
    while True:
        client, address = server_socket.accept()
        message = client.recv(BUFFER_SIZE).decode()
        if message != '#PING':
            print(f'Received "{message}" from {address}')
        if message[0] == '#':
            server_command(message)
        else:
            raise ValueError('Invalid message received')


# Function to ping the neighbor, and respond if unable to do so
def heartbeat():
    missed_beats = 0
    while True:
        if neighbor:
            try:
                utility.tcp_transmit_message('#PING', neighbor)
                sleep(0.2)
            except (ConnectionRefusedError, TimeoutError):
                missed_beats += 1
            if missed_beats > 4:                                                      # Once 5 beats have been missed
                print(f'{missed_beats} failed pings to neighbor, remove {neighbor}')  # print to console
                servers.remove(neighbor)                                              # remove the missing server
                missed_beats = 0                                                      # reset the count
                message_to_servers(f'#QUIT_server_0_{neighbor[0]}_{neighbor[1]}')     # inform the others
                neighbor_was_leader = neighbor == leader                              # check if neighbor was leader
                find_neighbor()                                                       # find a new neighbor
                if neighbor_was_leader:                                               # if the neighbor was the leader
                    print('Neighbor was leader, starting election')                   # print to console
                    start_voting()                                                    # start an election


# Function to handle the various commands that the server can receive
def server_command(command):
    match command.split('_'):
        # Sends the chat message to all clients other than the sender
        case ['#CHAT', sender_ip, sender_response_port, message]:
            message_to_clients(message, (sender_ip, int(sender_response_port)))
        # Add the provided client to this server's clients list
        # If the request came from the client (instead of another server) announce to the other clients
        # and inform the other servers
        case ['#JOIN', 'client', inform_others, ip, port]:
            if int(inform_others):  # Sending a 0/1 and casting to int is the easiest way I found to send bools as text
                message_to_clients(f'{ip} has joined the chat')
                message_to_servers(f'#JOIN_client_0_{ip}_{port}')
            if (ip, int(port)) not in clients:  # We NEVER want duplicates in our lists
                print(f'Adding {(ip, port)} to clients')
                clients.append((ip, int(port)))
        # Remove the provided client from this server's clients list
        # If the request came from the client (instead of another server) announce to the other clients
        # and inform the other servers
        case ['#QUIT', 'client', inform_others, ip, port]:
            print(f'Removing {(ip, port)} from clients')
            clients.remove((ip, int(port)))
            if int(inform_others):
                utility.tcp_transmit_message(f'#QUIT', (ip, int(port)))
                message_to_clients(f'{ip} has left the chat')
                message_to_servers(f'#QUIT_client_0_{ip}_{port}')
        # Add the provided server to this server's servers list
        # If the request came from the server to be added send it the whole clients and servers list
        # and inform the other servers
        case ['#JOIN', 'server', inform_others, ip, port]:
            if int(inform_others):
                transmit_state((ip, int(port)))
                message_to_servers(f'#JOIN_server_0_{ip}_{port}')
            if (ip, int(port)) not in servers:  # We NEVER want duplicates in our lists
                print(f'Adding {(ip, port)} to servers')
                servers.append((ip, int(port)))
                find_neighbor()
        # Remove the provided server from this server's servers list
        # If the request came from the server to be added inform the other servers
        case ['#QUIT', 'server', inform_others, ip, port]:
            server_to_remove = (ip, int(port))
            if server_to_remove == server_address:  # If we're told to remove ourself, something is wrong
                pass  # Will implement this later
            else:
                print(f'Removing {(ip, port)} from servers')
                servers.remove((ip, int(port)))
                if int(inform_others):
                    message_to_servers(f'#QUIT_server_0_{ip}_{port}')
                find_neighbor()
        # Receive a vote in the election
        # If I get a vote for myself then I've won the election
        # If not, then vote
        case ['#VOTE', ip, port]:
            address = (ip, int(port))
            if address == server_address:
                set_leader(server_address)
            else:
                start_voting((ip, int(port)))
        # Declaration that another server is the leader
        case ['#LEAD', ip, port]:
            set_leader((ip, int(port)))


# Sends message to all clients, excluding the sender
# If the message is "purely" a server message, then the server is the sender
# and the message is sent to all clients
def message_to_clients(message, sender=server_address):
    for client in clients:
        if client != sender:
            print(f'Send "{message}" to {client}')
            to_send = message
            if message[0] != '#':
                to_send += f'_{sender[0]}'
            try:
                utility.tcp_transmit_message(to_send, client)
            except (ConnectionRefusedError, TimeoutError):  # If we can't connect to a client, then drop it
                print(f'Failed send to {client}')
                print(f'Removing {client} from clients')
                clients.remove(client)
                message_to_servers(f'#QUIT_client_0_{client[0]}_{client[1]}')
                message_to_clients(f'{client[0]} is unreachable')


# Sends message to all connected servers, other than this server
def message_to_servers(message):
    for server in servers:
        if server != server_address:
            print(f'Send "{message}" to {server}')
            utility.tcp_transmit_message(message, server)


# Transmits the whole clients and servers lists to the provided address
def transmit_state(address):
    for client in clients:
        utility.tcp_transmit_message(f'#JOIN_client_0_{client[0]}_{client[1]}', address)
    for server in servers:
        utility.tcp_transmit_message(f'#JOIN_server_0_{server[0]}_{server[1]}', address)


"""
Voting is implemented with the find_neighbor, start_voting, and set_leader functions
The voting algorithm is the Chang and Roberts algorithm
https://en.wikipedia.org/wiki/Chang_and_Roberts_algorithm


I might try to change to a more efficient voting algorithm
Details here: J. Villadangos, A. Cordoba, F. Farina and M. Prieto, "Efficient leader election in complete networks"
"""


# Figure out who our neighbor is
# Our neighbor is the server with the next highest address
# The neighbors are used for crash fault tolerance
# and to arrange the servers in a virtual ring for voting
def find_neighbor():
    global neighbor
    length = len(servers)
    if length == 1:
        neighbor = None
        print('I have no neighbor')
        return
    servers.sort()
    index = servers.index(server_address)
    neighbor = servers[0] if index + 1 == length else servers[index + 1]
    print(f'My neighbor is {neighbor}')


# Starts voting by setting is_voting to true and sending a vote to neighbor
# If we're the only server, win automatically
# If we're the first server to vote, this will start the whole election
# and we just vote for ourself
# Otherwise, we vote for the min out of our address and the vote we received
def start_voting(address=server_address):
    if not neighbor:
        set_leader(server_address)
        return
    global is_voting
    vote_for = min(address, server_address)
    if vote_for != server_address or not is_voting:
        message = f'#VOTE_{vote_for[0]}_{vote_for[1]}'
        print(f'Send "{message}" to {vote_for}')
        utility.tcp_transmit_message(message, neighbor)
    is_voting = True


# Set the leader
# If I'm the leader, tell the clients and other servers
def set_leader(address):
    global leader, is_leader, is_voting
    leader = address
    is_leader = server_address == address
    is_voting = False
    if is_leader:
        print('I am the leader')
        message = f'#LEAD_{SERVER_IP}_{server_port}'
        message_to_clients(message)
        message_to_servers(message)
    else:
        print(f'The leader is {leader}')


if __name__ == '__main__':
    main()
