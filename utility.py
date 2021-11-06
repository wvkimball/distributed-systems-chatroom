#!/usr/bin/env python3.10
# Anything that would be repeated in both the server and the client code can/will go here
import socket
import os

# Constants
BROADCAST_PORT = 10002
BUFFER_SIZE = 1024
# Random code to broadcast / listen for to filter out other network traffic
BROADCAST_CODE = '9310e231f20a07cb53d96b90a978163d'
# Random code to respond with
RESPONSE_CODE = 'f56ddd73d577e38c45769dcd09dc9d99'


# source: https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
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


def tcp_transmit_message(message, address):
    transmit_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    transmit_socket.settimeout(1)
    transmit_socket.connect(address)
    transmit_socket.send(message.encode())
    transmit_socket.close()


def cls():
    os.system('cls' if os.name == 'nt' else 'clear')


def string_to_address(address_string):
    a = address_string[1:-1].split(', ')
    return a[0][1:-1], int(a[1])


# Create TCP socket for listening to unicast messages
def setup_tcp_listener_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((get_ip(), 0))
    s.listen()
    return s


def setup_udp_broadcast_socket(timeout=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    s.bind((get_ip(), 0))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # this is a broadcast socket
    if timeout:
        s.settimeout(timeout)
    return s
