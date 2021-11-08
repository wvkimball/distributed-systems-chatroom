#!/usr/bin/env python3.10

import socket
import threading
import sys
from utility import BUFFER_SIZE
import utility
from time import sleep

# Create TCP socket for listening to unicast messages
# The address tuple of this socket is the unique identifier for the client
client_socket = utility.setup_tcp_listener_socket()
client_address = client_socket.getsockname()

# Global variable to save the server address
server_address = None

# Flag to enable stopping the client
is_active = True


def main():
    utility.cls()
    broadcast_for_server()

    threading.Thread(target=transmit_messages).start()
    threading.Thread(target=tcp_listener).start()
    threading.Thread(target=multicast_listener).start()


# Broadcasts that this client is looking for a server
# This shouts into the void until a server is found
def broadcast_for_server():
    broadcast_socket = utility.setup_udp_broadcast_socket(timeout=2)

    while True:
        broadcast_socket.sendto(utility.BROADCAST_CODE.encode(), ('<broadcast>', utility.BROADCAST_PORT))
        print("Looking for server")
        # Wait for a response packet. If no packet has been received in 2 seconds, sleep then broadcast again
        try:
            data, address = broadcast_socket.recvfrom(1024)
            if data.startswith(f'{utility.RESPONSE_CODE}_{client_address[0]}'.encode()):
                message = data.decode().split('_')
                set_server_address((address[0], int(message[2])))
                print(f'Found server at {server_address[0]}')
                break
        except TimeoutError:
            sleep(3)

    broadcast_socket.close()
    message_to_server(f'#JOIN_client_1_{client_address}')


# Sets the server address which messages will be sent to
def set_server_address(address: tuple):
    global server_address
    server_address = address
    # print(f'\rServer address set to {address}\nYou: ', end='')


# Function to handle sending messages to the server
def transmit_messages():
    while is_active:
        message = input('\rYou: ')

        # If the flag has been changed while waiting for input, we exit
        if not is_active:
            sys.exit(0)

        # Send message
        if len(message) > BUFFER_SIZE / 2:
            print('Message is too long')
        elif len(message) == 0:
            continue
        elif message[0] == '#':
            client_command(message)
        else:
            message_to_server(f'#CHAT_{client_address}_{message}')


# Sends a message to the server
# If the server isn't there, the client starts searching again
def message_to_server(message):
    try:
        utility.tcp_transmit_message(message, server_address)
    except (ConnectionRefusedError, TimeoutError):
        print('\rError sending message, searching for server again')
        broadcast_for_server()


# Function to handle receiving tcp messages from the server
# Now that multicast has been implemented, these are just pings
# I might expand this for certain server commands later
def tcp_listener():
    client_socket.settimeout(2)
    while is_active:
        try:
            client, address = client_socket.accept()
        except TimeoutError:
            pass
        else:
            data = client.recv(BUFFER_SIZE).decode()
            parse_message(data)

    client_socket.close()
    sys.exit(0)


# Function to listen for messages multicasted to the client multicast group
def multicast_listener():
    # Create the socket
    m_listener_socket = utility.setup_multicast_listener_socket(utility.MG_CLIENT)
    m_listener_socket.settimeout(2)

    while is_active:
        try:
            data, address = m_listener_socket.recvfrom(BUFFER_SIZE)
        except TimeoutError:
            pass
        else:
            data = data.decode()
            data = data[data.index(')') + 1:]  # Trim the sending server address from the message
            m_listener_socket.sendto(b'ack', address)
            parse_message(data)

    m_listener_socket.close()
    sys.exit(0)


# Function to parse incoming messages to the client
def parse_message(data):
    if data[0] == '#':
        server_command(data)
    else:
        message, sender, nickname = data.split('_')
        sender = utility.string_to_address(sender)

        if sender == server_address:
            print(f'\r{message}')
        elif sender != client_address:
            print(f'\r{nickname if nickname else sender[0]}: {message}')
        print('\rYou: ' if is_active else '', end='')


# Handle commands entered by this client
def client_command(command):
    match command.split('_'):
        case ['#QUIT']:
            message_to_server(f'#QUIT_client_1_{client_address}')
            global is_active
            is_active = False
            print('Goodbye!')
            sys.exit(0)
        case ['#NICK', nickname]:
            message_to_server(f'#NICK_1_{client_address}_{nickname}')
        case ['#CLEAR']:
            utility.cls()
        case ['#DOWN', '0']:
            message_to_server('#DOWN_0')  # This only shuts down the lead server
        case ['#DOWN']:
            message_to_server('#DOWN_1')  # This triggers a shutdown for


# Handle commands received by this client from the server
def server_command(command):
    match command.split('_'):
        case ['#LEAD', address_string]:
            set_server_address(utility.string_to_address(address_string))
        case ['#DOWN']:
            global is_active
            is_active = False
            print('\rProgram is shutting down, press enter to exit.', end='')


if __name__ == '__main__':
    main()
