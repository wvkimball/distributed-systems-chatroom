#!/usr/bin/env python3.10
# Initial Source: https://github.com/digitalhhz/DSTutorial_Programmierprojekt/blob/master/simpleserver.py

import socket
import threading
import utility

# Create a UDP socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Bind the socket to the port
# server_address = '192.168.178.53'
server_address = utility.get_ip()
server_port = 10001

# Buffer size
buffer_size = utility.buffer_size

clients = []


def main():
    threading.Thread(target=broadcast_listener).start()
    threading.Thread(target=manage_chat).start()


def broadcast_listener():
    listener_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    listener_socket.bind(('', utility.broadcast_port))

    while True:
        data, address = listener_socket.recvfrom(1024)  # wait for a packet
        if data.startswith(utility.broadcast_code.encode()):
            print("Received broadcast from", address[0])
            send_message(utility.response_code, address)


def manage_chat():
    server_socket.bind((server_address, server_port))
    print('Server up and running at {}'.format(server_address))

    while True:
        data, address = server_socket.recvfrom(buffer_size)
        message = data.decode()
        print('Received message {} from client {}'.format(message, address))

        if data:
            send_message('#*#RECEIVED', address)
            # print('Replied to client: ', message)

        if message[0:3] == '#*#':
            server_command(message[3:], address)
        else:
            distribute_message(message, address)


# Handles commands sent to the server
def server_command(command, address):
    match command:
        case 'JOIN':
            clients.append(address)
            send_message('Welcome to the chat!', address)
            distribute_message('{} has joined the chat'.format(address[0]), address, True)
        case 'EXIT':
            clients.remove(address)
            send_message('#*#EXIT', address)
            distribute_message('{} has left the chat'.format(address[0]), address, True)


# Loops through all clients and sends the message to all but the sender
def distribute_message(message, sender, server_message=False):
    for client in clients:
        if client != sender:
            ident = ''
            if not server_message:
                ident = '{}: '.format(sender[0])
            send_message(ident + message, client)


# Sends a message to an address/client
def send_message(message, address):
    print('Send message {} to client {}'.format(message, address))
    server_socket.sendto(str.encode(message), address)


if __name__ == '__main__':
    main()
