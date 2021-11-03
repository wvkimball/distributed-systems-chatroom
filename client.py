#!/usr/bin/env python3.10

import socket
import threading
import sys
import utility
from time import sleep

# Get this clients IP address
client_ip = utility.get_ip()

# Create a UDP socket
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Create global variables which will be set by server response
server_ip = ''
server_port = 0

# Buffer size
buffer_size = utility.buffer_size


def main():
    broadcast_sender()

    send_message_to_server('#*#JOIN')

    threading.Thread(target=receive).start()
    threading.Thread(target=transmit).start()


# Broadcasts that this client is looking for a server
# This shouts into the void until a server is found
def broadcast_sender():
    broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    broadcast_socket.bind((client_ip, 0))
    broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # this is a broadcast socket
    broadcast_socket.settimeout(2)

    while True:
        broadcast_socket.sendto(utility.broadcast_code.encode(), ('<broadcast>', utility.broadcast_port))
        print("Looking for server")

        # Wait for a response packet. If no packet has been received in 2 seconds, sleep then broadcast again
        try:
            data, address = broadcast_socket.recvfrom(1024)
            if data.startswith((utility.response_code + client_ip).encode()):
                print("Found server at", address[0])
                set_server_address(address)
                break
        except TimeoutError:
            sleep(3)

    broadcast_socket.close()


# Sets the global variables for server address and port
# These can change if the leader server crashes
def set_server_address(address):
    global server_ip, server_port
    server_ip = address[0]
    server_port = address[1]


# Function to handle receiving messages from the server
def receive():
    while True:
        data, address = client_socket.recvfrom(buffer_size)
        if data:
            response = data.decode()
            if response[0:3] == '#*#':
                server_command(response[3:], address)
            else:
                print('\r' + response)
                print('\rYou: ', end='')


# Function to handle sending messages to the server
def transmit():
    while True:
        message = input('\rYou: ')
        # Send message
        if message[0:3] == '#*#':
            client_command(message[3:])
        else:
            send_message_to_server(message)


# This can be used to implement specific chat commands
def client_command(command):
    match command:
        case 'EXIT':
            send_message_to_server('#*#EXIT')
            sys.exit(0)


def server_command(command, address):
    match command:
        case 'EXIT':
            print('\rGoodbye!')
            client_socket.close()
            sys.exit(0)
        case 'SERV':
            print('\rChanged server to {}'.format(address[0]))
            set_server_address(address)
            print('\rYou: ', end='')


def send_message_to_server(message):
    client_socket.sendto(message.encode(), (server_ip, server_port))


if __name__ == '__main__':
    main()
