# Initial Source: https://github.com/digitalhhz/DSTutorial_Programmierprojekt/blob/master/simpleclient.py

import socket
import threading

# Create a UDP socket
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Bind the socket to the port
server_address = '127.0.0.1'
server_port = 10001

# Buffer size
buffer_size = 1024

# TODO: Get a 'You: ' prompt to play nice with the two threads


# Function to handle receiving messages from the server
def receive():
    while True:
        data, server = client_socket.recvfrom(buffer_size)
        if data:
            response = data.decode()
            if response[0:3] == '#*#':
                client_command(response[3:])
            else:
                print('\r' + response)


# Function to handle sending messages to the server
def transmit():
    while True:
        message = input('')
        if message == "EXIT":
            break
        # Send message
        client_socket.sendto(message.encode(), (server_address, server_port))


def main():
    try:

        client_socket.sendto('#*#JOIN'.encode(), (server_address, server_port))

        threading.Thread(target=receive).start()
        threading.Thread(target=transmit).start()

    finally:
        pass
        # client_socket.close()
        # print('Socket closed')


# This can be used to implement specific chat commands
def client_command(command):
    match command:
        case _:
            pass


if __name__ == '__main__':
    main()
