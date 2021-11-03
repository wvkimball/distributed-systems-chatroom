#!/usr/bin/env python3.10

import socket
import threading
import sys
import utility
from time import sleep

# Get this clients IP address
client_address = utility.get_ip()

# Create a UDP socket
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Create global variables which will be set by server response
server_address = ''
server_port = 0

# Buffer size
buffer_size = utility.buffer_size


def main():
    broadcast_sender()

    client_socket.sendto('#*#JOIN'.encode(), (server_address, server_port))

    threading.Thread(target=receive).start()
    threading.Thread(target=transmit).start()


def broadcast_sender():
    broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    broadcast_socket.bind((client_address, 0))
    broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # this is a broadcast socket
    broadcast_socket.settimeout(2)

    while True:
        broadcast_socket.sendto(utility.broadcast_code.encode(), ('<broadcast>', utility.broadcast_port))
        print("Looking for server")

        # Wait for a response packet. If no packet has been received in 2 seconds, sleep then broadcast again
        try:
            data, address = broadcast_socket.recvfrom(1024)
            if data.startswith((utility.response_code + client_address).encode()):
                print("Found server at", address[0])
                set_server_address(address)
                break
        except TimeoutError:
            sleep(3)

    broadcast_socket.close()


# Sets the global variables for server address and port
def set_server_address(address):
    global server_address, server_port
    server_address = address[0]
    server_port = address[1]


# Function to handle receiving messages from the server
def receive():
    while True:
        data, server = client_socket.recvfrom(buffer_size)
        if data:
            response = data.decode()
            if response[0:3] == '#*#':
                client_command(response[3:], True)
            else:
                print('\r' + response)
                print('\rYou: ', end='')


# Function to handle sending messages to the server
def transmit():
    while True:
        message = input('\rYou: ')
        # Send message
        client_socket.sendto(message.encode(), (server_address, server_port))
        if message[0:3] == '#*#':
            client_command(message[3:], False)


# This can be used to implement specific chat commands
def client_command(command, from_server):
    match command:
        case 'EXIT':
            if from_server:
                print('\rGoodbye!')
                client_socket.close()
            sys.exit(0)


if __name__ == '__main__':
    main()
