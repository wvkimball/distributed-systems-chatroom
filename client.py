#!/usr/bin/env python3.10

import threading
import sys
from time import sleep

from utility import BUFFER_SIZE, encode_message, decode_message, format_join_quit
import utility

# Create TCP socket for listening to unicast messages
# The address tuple of this socket is the unique identifier for the client
client_socket = utility.setup_tcp_listener_socket()
client_address = client_socket.getsockname()

# Global variable to save the server address
server_address = None

# Flag to enable stopping the client
is_active = True

clock = [0]


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
        except TimeoutError:
            pass
        else:
            if data.startswith(f'{utility.RESPONSE_CODE}_{client_address[0]}'.encode()):
                message = data.decode().split('_')
                set_server_address((address[0], int(message[2])))
                print(f'Found server at {server_address[0]}')
                break

    broadcast_socket.close()
    message_to_server('JOIN', format_join_quit('client', True, client_address))


# Sets the server address which messages will be sent to
def set_server_address(address: tuple):
    global server_address
    server_address = address


# Function to handle sending messages to the server
def transmit_messages():
    while is_active:
        message = input('\rYou: ')

        # This clears the just entered message from the chat using escape characters
        # Basic idea from here:
        # https://stackoverflow.com/questions/44565704/how-to-clear-only-last-one-line-in-python-output-console
        print(f'\033[A{" " * (len("You: " + message))}\033[A')

        # If the flag has been changed while waiting for input, we exit
        if not is_active:
            sys.exit(0)

        # Send message
        if len(message) > BUFFER_SIZE / 10:
            print('Message is too long')
        elif len(message) == 0:
            continue
        elif message[0] == '#':
            client_command(message)
        else:
            message_to_server('CHAT', message)


# Function to handle receiving tcp messages from the server
def tcp_listener():
    client_socket.settimeout(2)
    while is_active:
        try:
            client, address = client_socket.accept()
        except TimeoutError:
            pass
        else:
            message = decode_message(client.recv(BUFFER_SIZE))
            server_command(message)

    client_socket.close()
    sys.exit(0)


# Function to listen for messages multicasted to the client multicast group
def multicast_listener():
    sleep(0.5)
    # Create the socket
    m_listener_socket = utility.setup_multicast_listener_socket(utility.MG_CLIENT)
    m_listener_socket.settimeout(2)

    while is_active:
        try:
            data, address = m_listener_socket.recvfrom(BUFFER_SIZE)
        except TimeoutError:
            pass
        else:
            message = decode_message(data)
            m_listener_socket.sendto(b'ack', address)

            clock[0] += 1
            if clock[0] < message['clock'][0]:
                for i in range(clock[0], message['clock'][0]):
                    message_to_server('MSG', {'list': 'client', 'clock': [i]})
                    clock[0] += 1
                # This sleep allows the server time to send the missing messages
                sleep(0.5)

            if clock[0] != message['clock'][0]:
                raise ValueError(f'Clock is not correct, {clock =}')
            server_command(message)

    m_listener_socket.close()
    sys.exit(0)


# Sends a message to the server
# If no server is there, shutdown
def message_to_server(command, contents):
    message_bytes = encode_message(command, client_address, contents)
    try:
        utility.tcp_transmit_message(message_bytes, server_address)
    except (ConnectionRefusedError, TimeoutError):
        # print('\rError sending message, searching for server again')
        # broadcast_for_server()
        print('\rError sending message, server is unreachable')
        down()
        print('\rProgram is shutting down.')


# Handle commands entered by this client
def client_command(message):
    match message.split('_'):
        case ['#CLEAR']:
            utility.cls()
        case ['#QUIT']:
            message_to_server('QUIT', format_join_quit('client', True, client_address))
            down()
            print('\rGoodbye!')
        case ['#DOWN', '0']:
            message_to_server('DOWN', False)
        case ['#DOWN']:
            message_to_server('DOWN', True)


# Handle commands received by this client from the server
def server_command(message):
    match message:
        case {'command': 'CHAT', 'contents': {'chat_sender': address, 'chat_contents': chat_contents}}:
            if address != client_address:
                print(f'\r{address[0]}: {chat_contents}')
                print('\rYou: ' if is_active else '', end='')
            elif address == client_address:
                print(f'\rYou: {chat_contents}')
                print('\rYou: ' if is_active else '', end='')
        case {'command': 'SERV'}:
            print(f'\r{message["contents"]}')
            print('\rYou: ' if is_active else '', end='')
        case {'command': 'LEAD', 'sender': address}:
            set_server_address(address)
        case {'command': 'CLOCK', 'contents': client_clock}:
            global clock
            clock[0] = client_clock[0]
        case {'command': 'DOWN'}:
            down()
            print('\rProgram is shutting down, press enter to exit.', end='')


def down():
    global is_active
    is_active = False


if __name__ == '__main__':
    main()
