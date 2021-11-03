#!/usr/bin/env python3.10

import socket
import threading
from utility import BUFFER_SIZE
import utility
from time import time

# Constants
# Server connection data
SERVER_IP = utility_temp.get_ip()
SERVER_PORT = 10001
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

# Create TCP socket for listening
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(SERVER_ADDRESS)
server_socket.listen()

# List for clients
clients = []


def main():
    threading.Thread(target=broadcast_listener).start()
    threading.Thread(target=manage_chat).start()


# Function to listen for broadcasts from clients and respond when a broadcast is heard
def broadcast_listener():
    listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    listener_socket.bind(('', utility_temp.BROADCAST_PORT))

    print('Start listening for broadcasts')
    while True:
        data, address = listener_socket.recvfrom(BUFFER_SIZE)  # wait for a packet
        if data.startswith(utility_temp.BROADCAST_CODE.encode()):
            print("Received broadcast from", address[0])
            listener_socket.sendto(str.encode(f'{utility_temp.RESPONSE_CODE}_{address[0]}_{SERVER_PORT}'), address)


def add_client(address):
    # client = {'address': address, 'name': '', 'last_contact': time()}
    clients.append(address)


def manage_chat():
    while True:
        client, address = server_socket.accept()
        message = client.recv(BUFFER_SIZE).decode()
        print(f'Received {message} from {address}')

        if message[0] == '#':
            server_command(message)
        else:
            for client in clients:
                if client[0] != address[0]:
                    print(f'Send {message} to {client}')
                    utility_temp.transmit_message(f'{address[0]}_{message}', client)


def server_command(command):
    match command.split('_'):
        case ['#JOIN', client_ip, client_port]:
            print(f'Adding {(client_ip, client_port)} to clients')
            add_client((client_ip, int(client_port)))


if __name__ == '__main__':
    main()