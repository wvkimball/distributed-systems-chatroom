#!/usr/bin/env python3.10
# Anything that would be repeated in both the server and the client code can/will go here
import socket
import os
import struct
import ast

# Constants
# By changing the port numbers, there can be more than one chat on a network
BROADCAST_PORT = 10001
ML_SERVER_PORT = 10002
ML_CLIENT_PORT = 10003
BUFFER_SIZE = 4096
# Random code to broadcast / listen for to filter out other network traffic
BROADCAST_CODE = '9310e231f20a07cb53d96b90a978163d'
# Random code to respond with
RESPONSE_CODE = 'f56ddd73d577e38c45769dcd09dc9d99'
# Number of broadcasts made by a server at startup
SERVER_BROADCAST_ATTEMPTS = 5
# Addresses for multicast groups
# Block 224.3.0.64-224.3.255.255 is all unassigned
# Choices are arbitrary for now
MG_SERVER = ('224.3.100.255', ML_SERVER_PORT)
MG_CLIENT = ('224.3.200.255', ML_CLIENT_PORT)


# Function to get the ip address of the computer running the program
# This is used because socket.gethostbyname(socket.gethostname()) doesn't work well
# when you have more than one network adapter, or when 127.0.0.1 is saved in your hosts file in Linux
# Source: https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP


# Sends tcp messages by opening a new socket, connecting, sending the message, and then closing the socket
def tcp_transmit_message(message, address):
    transmit_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    transmit_socket.settimeout(1)
    transmit_socket.connect(address)
    transmit_socket.send(message)
    transmit_socket.close()


# Clears the console. Used at program launch
# Source: https://stackoverflow.com/questions/517970/how-to-clear-the-interpreter-console
def cls():
    os.system('cls' if os.name == 'nt' else 'clear')


# Create TCP socket for listening to unicast messages
def setup_tcp_listener_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((get_ip(), 0))
    s.listen()
    return s


# Create UDP socket for listening to broadcasted messages
def setup_udp_broadcast_socket(timeout=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    s.bind((get_ip(), 0))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # this is a broadcast socket
    if timeout:
        s.settimeout(timeout)
    return s


# Create UDP socket for listening to multicasted messages
# Understanding of / concept for the multicast functions from here:
# https://pymotw.com/3/socket/multicast.html
def setup_multicast_listener_socket(group):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # s.bind(('', group[1]))
    s.bind(group)

    group = socket.inet_aton(group[0])
    mreq = struct.pack('4sL', group, socket.INADDR_ANY)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    return s


def encode_message(command, sender, contents='', clock=None):
    message_dict = {'command': command, 'sender': sender, 'contents': contents, 'clock': clock}
    return repr(message_dict).encode()


def decode_message(message):
    return ast.literal_eval(message.decode())


def format_join_quit(node_type, inform_others, address):
    return {'node_type': node_type, 'inform_others': inform_others, 'address': address}
