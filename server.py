#!/usr/bin/env python3.10

import socket
import sys
import threading
from utility import BUFFER_SIZE
import utility
from time import sleep

# Create TCP socket for listening to unicast messages
# The address tuple of this socket is the unique identifier for the server
server_socket = utility.setup_tcp_listener_socket()
server_address = server_socket.getsockname()

# Lists for connected clients and servers
clients = []
nicknames = {}
servers = [server_address]  # Server list starts with this server in it

# Variables for leadership and voting
leader_address = None
is_leader = False
is_voting = False
neighbor = None

# Flag to enable stopping the client
is_active = True


def main():
    utility.cls()
    startup_broadcast()

    threading.Thread(target=broadcast_listener).start()
    threading.Thread(target=tcp_listener).start()
    threading.Thread(target=multicast_listener).start()
    threading.Thread(target=heartbeat).start()


# Broadcasts looking for another active server
def startup_broadcast():
    broadcast_socket = utility.setup_udp_broadcast_socket(timeout=1)

    got_response = False

    # 5 attempts are made to find another server
    # After this, the server assumes it is the only one and considers itself leader
    for i in range(0, 5):
        broadcast_socket.sendto(utility.BROADCAST_CODE.encode(), ('<broadcast>', utility.BROADCAST_PORT))
        print("Looking for other servers")

        # Wait for a response packet. If no packet has been received in 1 second, broadcast again
        try:
            data, address = broadcast_socket.recvfrom(1024)
            if data.startswith(f'{utility.RESPONSE_CODE}_{server_address[0]}'.encode()):
                print("Found server at", address[0])
                response_port = int(data.decode().split('_')[2])
                tcp_transmit_message(f'#JOIN_server_1_{server_address}', (address[0], response_port))
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
    listener_socket.settimeout(2)

    while is_active:
        try:
            data, address = listener_socket.recvfrom(BUFFER_SIZE)  # wait for a packet
        except TimeoutError:
            pass
        else:
            if is_leader and data.startswith(utility.BROADCAST_CODE.encode()):
                print(f'Received broadcast from {address[0]}, replying with response code')
                # Respond with the response code, the IP we're responding to, and the the port we're listening with
                listener_socket.sendto(str.encode(f'{utility.RESPONSE_CODE}_{address[0]}_{server_address[1]}'), address)

    print('Broadcast listener closing')
    listener_socket.close()
    sys.exit(0)


# Function to manage the chat
# passes valid commands to server_command
def tcp_listener():
    server_socket.settimeout(2)
    while is_active:
        try:
            client, address = server_socket.accept()
        except TimeoutError:
            pass
        else:
            message = client.recv(BUFFER_SIZE).decode()
            if message != '#PING':  # We don't print pings since that gets a bit overwhelming
                print(f'Received "{message}" from {address}')
            if message[0] == '#':
                server_command(message)
            else:
                raise ValueError('Invalid message received')

    print('Unicast listener closing')
    server_socket.close()
    sys.exit(0)


# Listens for multicasted messages
def multicast_listener():
    # Create the socket
    m_listener_socket = utility.setup_multicast_listener_socket(utility.MG_SERVER)
    m_listener_socket.settimeout(2)

    while is_active:
        try:
            data, address = m_listener_socket.recvfrom(BUFFER_SIZE)
        except TimeoutError:
            pass
        else:
            if data.startswith(f'{server_address}'.encode()):
                continue  # If we've picked up our own message, ignore it
            data = data.decode()
            message = data[data.index(')')+1:]  # Trim the sending server address from the message
            print(f'Received multicast {message} from {address}, sending acknowledgement')
            m_listener_socket.sendto(b'ack', address)
            if message[0] == '#':
                server_command(message)
            else:
                raise ValueError('Invalid message received')

    print('Multicast listener closing')
    m_listener_socket.close()
    sys.exit(0)


# Transmits multicast messages and checks how many responses are received
def multicast_transmit_message(message, group=utility.MG_SERVER):
    match group:
        case utility.MG_SERVER:
            expected_responses = len(servers) - 1
            send_to = 'servers'
        case utility.MG_CLIENT:
            expected_responses = len(clients)
            send_to = 'clients'
        case _:
            raise ValueError('Invalid multicast group')

    if not expected_responses:  # If there are no expected responses, then don't bother transmitting
        return

    print(f'Sending multicast "{message}" to {send_to}')

    # Create the socket
    m_sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    m_sender_socket.settimeout(0.2)
    m_sender_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

    responses = 0

    try:
        # Send data to the multicast group
        send = f'{server_address}{message}'.encode()
        m_sender_socket.sendto(send, group)

        # Look for responses from all recipients
        while True:
            try:
                data, server = m_sender_socket.recvfrom(16)
            except TimeoutError:
                break
            else:
                responses += 1
    finally:
        print(f'Received {responses} of {expected_responses} expected responses')
        m_sender_socket.close()
        if group == utility.MG_CLIENT and responses < expected_responses:
            ping_clients()


# Function to ping the neighbor, and respond if unable to do so
def heartbeat():
    missed_beats = 0
    while is_active:
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
                tcp_to_servers(f'#QUIT_server_0_{neighbor}')                          # inform the others
                neighbor_was_leader = neighbor == leader_address                      # check if neighbor was leader
                find_neighbor()                                                       # find a new neighbor
                if neighbor_was_leader:                                               # if the neighbor was the leader
                    print('Previous neighbor was leader, starting election')          # print to console
                    start_voting()                                                    # start an election

    print('Heartbeat thread closing')
    sys.exit(0)


# Function to handle the various commands that the server can receive
def server_command(command):
    match command.split('_'):
        # Sends the chat message to all clients other than the sender
        case ['#CHAT', address_string, message]:
            address = utility.string_to_address(address_string)
            message_to_clients(message, address)
        # Sets a nickname for the client
        case ['#NICK', inform_others, address_string, nickname]:
            address = utility.string_to_address(address_string)
            print(f'Changing nickname of {address} to {nickname}')
            add_nickname(address, nickname)
            if int(inform_others):
                message_to_clients(f'{address[0]} changed name to {nicknames[address]}')
                message_to_servers(f'#NICK_0_{address}_{nicknames[address]}')
        # Add the provided client to this server's clients list
        # If the request came from the client (instead of another server) announce to the other clients
        # and inform the other servers
        case ['#JOIN', 'client', inform_others, address_string]:
            address = utility.string_to_address(address_string)
            if int(inform_others):  # Sending a 0/1 and casting to int is the easiest way I found to send bools as text
                message_to_clients(f'{address[0]} has joined the chat')
                message_to_servers(f'#JOIN_client_0_{address}')
            if address not in clients:  # We NEVER want duplicates in our lists
                print(f'Adding {address} to clients')
                clients.append(address)
        # Remove the provided client from this server's clients list
        # If the request came from the client (instead of another server) announce to the other clients
        # and inform the other servers
        case ['#QUIT', 'client', inform_others, address_string]:
            address = utility.string_to_address(address_string)
            print(f'Removing {address} from clients')
            try:
                clients.remove(address)
                remove_nickname(address)
            except ValueError:
                print(f'{address} was not in clients, it was likely removed by the ping')
            if int(inform_others):
                message_to_clients(f'{address[0]} has left the chat')
                message_to_servers(f'#QUIT_client_0_{address}')
        # Add the provided server to this server's servers list
        # If the request came from the server to be added send it the whole clients and servers list
        # and inform the other servers
        case ['#JOIN', 'server', inform_others, address_string]:
            address = utility.string_to_address(address_string)
            if int(inform_others):
                transmit_state(address)
                message_to_servers(f'#JOIN_server_0_{address}')
            if address not in servers:  # We NEVER want duplicates in our lists
                print(f'Adding {address} to servers')
                servers.append(address)
                find_neighbor()
        # Remove the provided server from this server's servers list
        # If the request came from the server to be added inform the other servers
        case ['#QUIT', 'server', inform_others, address_string]:
            address = utility.string_to_address(address_string)
            if address == server_address:  # If we're told to remove ourself, something is wrong
                pass  # Will implement this later
            else:
                print(f'Removing {address} from servers')
                servers.remove(address)
                if int(inform_others):
                    message_to_servers(f'#QUIT_server_0_{address}')
                find_neighbor()
        # Receive a vote in the election
        # If I get a vote for myself then I've won the election
        # If not, then vote
        case ['#VOTE', address_string]:
            address = utility.string_to_address(address_string)
            if address == server_address:
                set_leader(server_address)
            else:
                start_voting(address)
        # Declaration that another server is the leader
        case ['#LEAD', address_string]:
            address = utility.string_to_address(address_string)
            if address != server_address:
                set_leader(address)
                message = f'#LEAD_{leader_address}'
                tcp_transmit_message(message, neighbor)
        case ['#DOWN', inform_others]:
            if int(inform_others):
                # tcp_to_servers('#DOWN_0')
                message_to_clients('#DOWN')
                message_to_servers('#DOWN_0')
            print(f'Shutting down server at {server_address}')
            global is_active
            is_active = False


# If a specific client is provided, ping that client
# Otherwise ping all clients
def ping_clients(client_to_ping=None):
    if client_to_ping:
        to_ping = [client_to_ping]
    else:
        to_ping = clients
    for client in to_ping:
        try:
            utility.tcp_transmit_message('#PING', client)
        except (ConnectionRefusedError, TimeoutError):  # If we can't connect to a client, then drop it
            print(f'Failed send to {client}')
            print(f'Removing {client} from clients')
            try:
                clients.remove(client)
                remove_nickname(client)
                message_to_servers(f'#QUIT_client_0_{client}')
                message_to_clients(f'{client[0]} is unreachable')
            except ValueError:
                print(f'{client} was not in clients')


# Sends message to all clients, specifying who the sender is
# If the message is "purely" a server message, then the server is the sender
def message_to_clients(message, sender=server_address):
    to_send = message
    if message[0] != '#':
        to_send += f'_{sender}_{nicknames[sender] if sender in nicknames else ""}'
    multicast_transmit_message(to_send, utility.MG_CLIENT)


# Adds a nickname to the dictionary. If the nickname already exists, then appends the client's ip
def add_nickname(address, nickname):
    if nickname in nicknames.values():
        nicknames[address] = f'{nickname} ({address[0]})'
    else:
        nicknames[address] = nickname


# Removes a nickname from the dictionary
def remove_nickname(address):
    try:
        del nicknames[address]
    except KeyError:
        pass


# Sends a multicast message to all servers
def message_to_servers(message):
    multicast_transmit_message(message, utility.MG_SERVER)


def tcp_to_servers(message):
    for server in [s for s in servers if s != server_address]:
        try:
            tcp_transmit_message(message, server)
        except (ConnectionRefusedError, TimeoutError):
            print(f'Unable to send to {server}')


# Transmits the whole clients and servers lists to the provided address
def transmit_state(address):
    for client in clients:
        tcp_transmit_message(f'#JOIN_client_0_{client}', address)
    for server in servers:
        tcp_transmit_message(f'#JOIN_server_0_{server}', address)


# Sends message to address and prints to the console
def tcp_transmit_message(message, address):
    print(f'Send "{message}" to {address}')
    utility.tcp_transmit_message(message, address)


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
        message = f'#VOTE_{vote_for}'
        tcp_transmit_message(message, neighbor)
    is_voting = True


# Set the leader
# If I'm the leader, tell the clients and other servers
def set_leader(address):
    global leader_address, is_leader, is_voting
    leader_address = address
    is_leader = server_address == address
    is_voting = False
    if is_leader:
        print('I am the leader')
        message = f'#LEAD_{server_address}'
        message_to_clients(message)
        if neighbor:
            tcp_transmit_message(message, neighbor)
    else:
        print(f'The leader is {leader_address}')


if __name__ == '__main__':
    main()
