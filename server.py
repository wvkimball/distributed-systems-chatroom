#!/usr/bin/env python3.10

import socket
import threading
from utility import BUFFER_SIZE
import utility
from time import time

# Constants
# Server connection data
SERVER_IP = utility.get_ip()
SERVER_PORT = 10001
SERVER_ADDRESS = (SERVER_IP, SERVER_PORT)

# Create TCP socket for listening
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(SERVER_ADDRESS)
server_socket.listen()

# Lists for connected clients and servers
clients = []
servers = [SERVER_ADDRESS]


def main():
    threading.Thread(target=broadcast_listener).start()
    threading.Thread(target=manage_chat).start()


# Function to listen for broadcasts from clients and respond when a broadcast is heard
def broadcast_listener():
    print('Server up and running at {}'.format(SERVER_IP))

    listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    listener_socket.bind(('', utility.BROADCAST_PORT))

    while True:
        data, address = listener_socket.recvfrom(BUFFER_SIZE)  # wait for a packet
        if data.startswith(utility.BROADCAST_CODE.encode()):
            print("Received broadcast from", address[0])
            # Respond with the response code, the IP we're responding to, and the the port we're listening with
            listener_socket.sendto(str.encode(f'{utility.RESPONSE_CODE}_{address[0]}_{SERVER_PORT}'), address)


def manage_chat():
    while True:
        client, address = server_socket.accept()
        message = client.recv(BUFFER_SIZE).decode()
        print(f'Received "{message}" from {address}')

        if message[0] == '#':
            server_command(message)
        else:
            message_to_clients(message, address)


def server_command(command):
    match command.split('_'):
        # Add the provided client to this servers client list
        # If the request came from the client (instead of another server) announce to the other clients
        case ['#JOIN', 'client', from_client, client_ip, client_port]:
            print(f'Adding {(client_ip, client_port)} to clients')
            if from_client:
                message_to_clients(f'{client_ip} has joined the chat', SERVER_ADDRESS)
                message_to_servers(f'#JOIN_client_False_{client_ip}_{client_port}')
            clients.append((client_ip, int(client_port)))
        # Remove the provided client from this servers client list
        # If the request came from the client (instead of another server) announce to the other clients
        case ['#QUIT', 'client', from_client, client_ip, client_port]:
            print(f'Removing {(client_ip, client_port)} from clients')
            clients.remove((client_ip, int(client_port)))
            if from_client:
                utility.tcp_transmit_message(f'{SERVER_IP}_#QUIT', (client_ip, int(client_port)))
                message_to_clients(f'{client_ip} has left the chat', SERVER_ADDRESS)
                message_to_servers(f'#JOIN_client_False_{client_ip}_{client_port}')


# Sends message to all clients, excluding the sender
# If the message is "purely" a server message, then the server is the sender
# and the message is sent to all clients
def message_to_clients(message, sender):
    for client in clients:
        if client[0] != sender[0]:
            print(f'Send "{message}" to {client}')
            utility.tcp_transmit_message(f'{sender[0]}_{message}', client)


# Sends message to all connected servers, other than this server
def message_to_servers(message):
    for server in servers:
        if server[0] != SERVER_IP:
            print(f'Send "{message}" to {server}')
            utility.tcp_transmit_message(message, server)


if __name__ == '__main__':
    main()
