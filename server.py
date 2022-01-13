#!/usr/bin/env python3.10

import socket
import sys
import threading
from utility import BUFFER_SIZE, encode_message, decode_message, format_join_quit
import utility
from time import sleep


# Create TCP socket for listening to unicast messages
# The address tuple of this socket is the unique identifier for the server
server_socket = utility.setup_tcp_listener_socket()
server_address = server_socket.getsockname()

# Lists for connected clients and servers
clients = []
servers = [server_address]  # Server list starts with this server in it

# Variables for leadership and voting
leader_address = None
is_leader = False
is_voting = False
neighbor = None

# Flag to enable stopping the client
is_active = True

# Counts for server and client multicasts
server_clock = [0]
client_clock = [0]

# Dicts for the server and client mulitcast messages
server_multi_msgs = {}
client_multi_msgs = {}
# How many messages we want to store in the dictionaries
keep_msgs = 5


def main():
    utility.cls()
    startup_broadcast()

    threading.Thread(target=broadcast_listener).start()
    threading.Thread(target=tcp_listener).start()
    threading.Thread(target=heartbeat).start()
    threading.Thread(target=multicast_listener, args=(utility.MG_SERVER,)).start()
    threading.Thread(target=multicast_listener, args=(utility.MG_CLIENT,)).start()


# Broadcasts looking for another active server
def startup_broadcast():
    broadcast_socket = utility.setup_udp_broadcast_socket(timeout=1)

    got_response = False

    # 5 attempts are made to find another server
    # After this, the server assumes it is the only one and considers itself leader
    for i in range(0, utility.SERVER_BROADCAST_ATTEMPTS):
        broadcast_socket.sendto(utility.BROADCAST_CODE.encode(), ('<broadcast>', utility.BROADCAST_PORT))
        print("Looking for other servers")

        # Wait for a response packet. If no packet has been received in 1 second, broadcast again
        try:
            data, address = broadcast_socket.recvfrom(1024)
            if data.startswith(f'{utility.RESPONSE_CODE}_{server_address[0]}'.encode()):
                print("Found server at", address[0])
                response_port = int(data.decode().split('_')[2])
                join_contents = {'node_type': 'server', 'inform_others': True, 'address': server_address}
                tcp_transmit_message('JOIN', join_contents, (address[0], response_port))
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
    print(f'Server up and running at {server_address}')

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


# Listens for multicasted messages
def multicast_listener(group):
    match group:
        case utility.MG_SERVER:
            name = 'server'
            clock = server_clock
            multi_msgs = server_multi_msgs
        case utility.MG_CLIENT:
            name = 'client'
            clock = client_clock
            multi_msgs = client_multi_msgs
        case _:
            raise ValueError('Invalid multicast group')

    # Create the socket
    m_listener_socket = utility.setup_multicast_listener_socket(group)
    m_listener_socket.settimeout(2)

    while is_active:
        try:
            data, address = m_listener_socket.recvfrom(BUFFER_SIZE)
        except TimeoutError:
            pass
        else:
            message = decode_message(data)
            # If we've picked up our own message
            # Or the message has a lower clock than the next expected message
            # Ignore it
            if message['sender'] == server_address or message['clock'][0] <= clock[0]:
                continue

            print(f'Listener {name} received multicast command {message["command"]} from {message["sender"]}')
            m_listener_socket.sendto(b'ack', address)

            clock[0] += 1
            # Causal ordering doesn't really matter here.
            # Just has to be reliable
            for i in range(clock[0], message['clock'][0]):
                print(f'Requesting missing {name} message with clock {i}')
                tcp_transmit_message('MSG', {'list': name, 'clock': [i]}, message['sender'])
                clock[0] += 1

            if clock[0] != message['clock'][0]:
                raise ValueError(f'Clock is not correct, {clock =}')
            multi_msgs[str(clock[0])] = {'command': message["command"], 'contents': message["contents"]}
            if len(multi_msgs) > keep_msgs:
                multi_msgs.pop(next(iter(multi_msgs)))
            parse_multicast(message, group)

    print(f'Multicast listener {name} closing')
    m_listener_socket.close()
    sys.exit(0)


def parse_multicast(message, group):
    match group:
        case utility.MG_SERVER:
            server_command(message)
        case utility.MG_CLIENT:
            pass
        case _:
            raise ValueError(f'Invalid multicast group, {group =}')


# Transmits multicast messages and checks how many responses are received
def multicast_transmit_message(command, contents, group):
    len_other_servers = len(servers) - 1  # We expect responses from every other than the sender
    len_clients = len(clients)

    match group:
        case utility.MG_SERVER:
            if not len_other_servers:  # If there are no other servers, don't bother transmitting
                return
            expected_responses = len_other_servers
            send_to = 'servers'
            multi_msgs = server_multi_msgs
            clock = server_clock
        case utility.MG_CLIENT:
            if not len_clients:  # If there are no clients, don't bother transmitting
                return
            expected_responses = len_clients + len_other_servers
            send_to = 'clients'
            multi_msgs = client_multi_msgs
            clock = client_clock
        case _:
            raise ValueError('Invalid multicast group')

    clock[0] += 1
    print(f'Sending multicast command {command} to {send_to} with clock {clock[0]}')

    # Create the socket
    m_sender_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    m_sender_socket.settimeout(0.2)
    m_sender_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

    responses = 0

    try:
        # Send message to the multicast group
        message_bytes = encode_message(command, server_address, contents, clock)
        m_sender_socket.sendto(message_bytes, group)

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

    multi_msgs[str(clock[0])] = {'command': command, 'contents': contents}
    if len(multi_msgs) > keep_msgs:
        multi_msgs.pop(next(iter(multi_msgs)))


# Function to listen for tcp (unicast) messages
# passes valid commands to server_command
def tcp_listener():
    server_socket.settimeout(2)
    while is_active:
        try:
            client, address = server_socket.accept()
        except TimeoutError:
            pass
        else:
            message = decode_message(client.recv(BUFFER_SIZE))
            if message['command'] != 'PING':  # We don't print pings since that would be a lot
                print(f'Command {message["command"]} received from {message["sender"]}')
            server_command(message)

    print('Unicast listener closing')
    server_socket.close()


# Function to ping the neighbor, and respond if unable to do so
def heartbeat():
    missed_beats = 0
    while is_active:
        if neighbor:
            try:
                tcp_transmit_message('PING', '', neighbor)
                sleep(0.2)
            except (ConnectionRefusedError, TimeoutError):
                missed_beats += 1
            else:
                missed_beats = 0
            if missed_beats > 4:                                                         # Once 5 beats have been missed
                print(f'{missed_beats} failed pings to neighbor, remove {neighbor}')     # print to console
                servers.remove(neighbor)                                                 # remove the missing server
                missed_beats = 0                                                         # reset the count
                tcp_msg_to_servers('QUIT', format_join_quit('server', False, neighbor))  # inform the others
                neighbor_was_leader = neighbor == leader_address                         # check if neighbor was leader
                find_neighbor()                                                          # find a new neighbor
                if neighbor_was_leader:                                                  # if the neighbor was leader
                    print('Previous neighbor was leader, starting election')             # print to console
                    vote()                                                               # start an election

    print('Heartbeat thread closing')
    sys.exit(0)


def server_command(message):
    match message:
        # Sends the chat message to all clients
        # The client is responsible for not printing messages it originally sent
        case {'command': 'CHAT', 'sender': sender, 'contents': contents}:
            chat_message = {'chat_sender': sender, 'chat_contents': contents}
            message_to_clients('CHAT', chat_message)
        # Add the provided node to this server's list
        # If the request came from the node to be added inform the other servers
        # If the node is a server, send it the server and client lists
        case {'command': 'JOIN',
              'contents': {'node_type': node_type, 'inform_others': inform_others, 'address': address}}:
            if node_type == 'server':
                node_list = servers
            elif node_type == 'client':
                node_list = clients
            else:
                raise ValueError(f'Tried to add invalid node type: {node_type =}')

            if inform_others:
                message_to_servers('JOIN', format_join_quit(node_type, False, address))
                if node_type == 'client':
                    message_to_clients('SERV', f'{address[0]} has joined the chat')
                    tcp_transmit_message('CLOCK', client_clock, address)
                elif node_type == 'server':
                    transmit_state(address)

            if address not in node_list:  # We NEVER want duplicates in our lists
                print(f'Adding {address} to {node_type} list')
                node_list.append(address)
                if node_type == 'server':
                    find_neighbor()
        # Remove the provided node to this server's list
        # If the request came from the node to be removed inform the other servers
        # If the node is a client, then inform the other clients
        case {'command': 'QUIT',
              'contents': {'node_type': node_type, 'inform_others': inform_others, 'address': address}}:
            if node_type == 'server':
                node_list = servers
            elif node_type == 'client':
                node_list = clients
            else:
                raise ValueError(f'Tried to remove invalid node type: {node_type =}')

            if inform_others:
                if node_type == 'client':
                    message_to_clients('SERV', f'{address[0]} has left the chat')
                message_to_servers('QUIT', format_join_quit(node_type, False, address))
            try:
                print(f'Removing {address} from {node_type} list')
                node_list.remove(address)
                if node_type == 'server':
                    find_neighbor()
            except ValueError:
                print(f'{address} was not in {node_type} list')
        # Calls a function to import the current state from the leader
        # This is split of for readability and to keep global overwriting of the lists out of this function
        case {'command': 'STATE', 'contents': state}:
            receive_state(state)
        # Receive a vote in the election
        # If I get a vote for myself then I've won the election. If not, then vote
        # If the leader has been elected then set the new leader
        case {'command': 'VOTE', 'contents': {'vote_for': address, 'leader_elected': leader_elected}}:
            if not leader_elected:
                if address == server_address:
                    set_leader(server_address)
                else:
                    vote(address)
            else:
                if address != server_address:
                    set_leader(address)
                    tcp_transmit_message('VOTE', {'vote_for': address, 'leader_elected': True}, neighbor)
        # Replies with the requested message to the requesting server
        case {'command': 'MSG', 'contents': {'list': list_type, 'clock': msg_clock}, 'sender': address}:
            if list_type == 'server':
                multi_msgs = server_multi_msgs
            elif list_type == 'client':
                multi_msgs = client_multi_msgs
            else:
                ValueError(f'Message requested from invalid list, {list_type =}')

            message = multi_msgs[str(msg_clock[0])]
            print(f'{message =}')
            tcp_transmit_message(message['command'], message['contents'], address)
        # Either shutdown just this server (for testing leader election)
        # Or shutdown the whole chatroom
        case {'command': 'DOWN', 'contents': inform_others}:
            if inform_others:
                tcp_msg_to_clients('DOWN')
                tcp_msg_to_servers('DOWN')
            print(f'Shutting down server at {server_address}')
            global is_active
            is_active = False


def message_to_servers(command, contents=''):
    multicast_transmit_message(command, contents, utility.MG_SERVER)


# Sends message to all servers
def tcp_msg_to_servers(command, contents=''):
    for server in [s for s in servers if s != server_address]:
        try:
            tcp_transmit_message(command, contents, server)
        except (ConnectionRefusedError, TimeoutError):
            print(f'Unable to send to {server}')


# Transmits the current server and client lists from the leader to the new server
# Will be expanded later for clocks
def transmit_state(address):
    state = {'servers': servers, 'clients': clients,
             'server_clock': server_clock, 'client_clock': client_clock,
             'server_multi_msgs': server_multi_msgs, 'client_multi_msgs': client_multi_msgs}
    tcp_transmit_message('STATE', state, address)


# Receives the current server and client lists from the leader
# Will be expanded later for clocks
def receive_state(state):
    global servers, clients, server_clock, client_clock, server_multi_msgs, client_multi_msgs

    servers = [server_address]        # Clear the server list (except for this server)
    servers.extend(state["servers"])  # Add the received list to the servers
    servers = list(set(servers))      # Remove any duplicates
    find_neighbor()                   # Find neighbor (also takes care of sorting)

    clients = []                      # Clear the client list
    clients.extend(state["clients"])  # Add the received list to the clients
    clients = list(set(clients))      # Remove any duplicates

    server_clock[0] = state["server_clock"][0]
    client_clock[0] = state["client_clock"][0]

    server_multi_msgs = state["server_multi_msgs"]
    client_multi_msgs = state["client_multi_msgs"]


def message_to_clients(command, contents=''):
    multicast_transmit_message(command, contents, utility.MG_CLIENT)


# Sends message to all clients
def tcp_msg_to_clients(command, contents=''):
    # This lets us iterate through the list even if we remove an element partway through
    client_list = list(clients)
    for client in client_list:
        try:
            tcp_transmit_message(command, contents, client)
        except (ConnectionRefusedError, TimeoutError):
            print(f'Unable to send to {client}')
            ping_clients(client)


# If a specific client is provided, ping that client
# Otherwise ping all clients
def ping_clients(client_to_ping=None):
    if client_to_ping:
        to_ping = [client_to_ping]
    else:
        to_ping = clients

    for client in to_ping:
        try:
            tcp_transmit_message('PING', '', client)
        except (ConnectionRefusedError, TimeoutError):  # If we can't connect to a client, then drop it
            print(f'Failed send to {client}')
            print(f'Removing {client} from clients')
            try:
                clients.remove(client)
                message_to_servers('QUIT', format_join_quit('client', False, client))
                message_to_clients('SERV', f'{client[0]} is unreachable')
            except ValueError:
                print(f'{client} was not in clients')


def tcp_transmit_message(command, contents, address):
    if command != 'PING':
        print(f'Sending command {command} to {address}')
    message_bytes = encode_message(command, server_address, contents)
    utility.tcp_transmit_message(message_bytes, address)


"""
Voting is implemented with the find_neighbor, start_voting, and set_leader functions
The voting algorithm is the LaLann-Chang-Roberts algorithm
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
# Otherwise, we vote for the max out of our address and the vote we received
def vote(address=server_address):
    if not neighbor:
        set_leader(server_address)
        return
    global is_voting
    vote_for = max(address, server_address)
    if vote_for != server_address or not is_voting:
        tcp_transmit_message('VOTE', {'vote_for': vote_for, 'leader_elected': False}, neighbor)
    is_voting = True


def set_leader(address):
    global leader_address, is_leader, is_voting
    leader_address = address
    is_leader = leader_address == server_address
    is_voting = False
    if is_leader:
        print('I am the leader')
        message_to_clients('LEAD')
        if neighbor:
            tcp_transmit_message('VOTE', {'vote_for': server_address, 'leader_elected': True}, neighbor)
    else:
        print(f'The leader is {leader_address}')


if __name__ == '__main__':
    main()
