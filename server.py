# Initial Source: https://github.com/digitalhhz/DSTutorial_Programmierprojekt/blob/master/simpleserver.py

import socket
import threading

# Create a UDP socket
server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Bind the socket to the port
server_address = '127.0.0.1'
server_port = 10001

# Buffer size
buffer_size = 1024

clients = []


def main():
    server_socket.bind((server_address, server_port))
    print('Server up and running at {}:{}'.format(server_address, server_port))

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
            broadcast(message, address)


def server_command(command, address):
    match command:
        case 'JOIN':
            clients.append(address)
            send_message('Welcome to the chat!', address)
        case 'EXIT':
            clients.remove(address)
            send_message('#*#EXIT', address)


# Loops through all clients and sends the message to all but the sender
def broadcast(message, sender):
    for client in clients:
        if client != sender:
            send_message('{}:{}: '.format(sender[0], sender[1]) + message, client)


# Sends a message to an address/client
def send_message(message, address):
    print('Send message {} to client {}'.format(message, address))
    server_socket.sendto(str.encode(message), address)


if __name__ == '__main__':
    main()
