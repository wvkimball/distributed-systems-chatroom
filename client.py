import socket
import threading
import sys
from utility import BUFFER_SIZE
import utility
from time import sleep

# Constants
CLIENT_IP = utility.get_ip()
CLIENT_PORT = 10001

# Create TCP socket for listening
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.bind((CLIENT_IP, CLIENT_PORT))
client_socket.listen()

# Create global variables which will be set by server response
server_ip = ''
server_port = 0
server_address = (server_ip, server_port)


def main():
    broadcast_for_server()

    threading.Thread(target=transmit_messages).start()
    threading.Thread(target=receive_messages).start()


# Broadcasts that this client is looking for a server
# This shouts into the void until a server is found
def broadcast_for_server():
    broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # create UDP socket
    broadcast_socket.bind((CLIENT_IP, 0))
    broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # this is a broadcast socket
    broadcast_socket.settimeout(2)

    while True:
        broadcast_socket.sendto(utility.BROADCAST_CODE.encode(), ('<broadcast>', utility.BROADCAST_PORT))
        print("Looking for server")
        # Wait for a response packet. If no packet has been received in 2 seconds, sleep then broadcast again
        try:
            data, address = broadcast_socket.recvfrom(1024)
            if data.startswith((utility.RESPONSE_CODE + '_' + CLIENT_IP).encode()):
                message = data.decode().split('_')
                print("Found server at", address[0])
                set_server_address((address[0], int(message[2])))
                break
        except TimeoutError:
            sleep(3)

    broadcast_socket.close()


# Sets the server address which messages will be sent to
def set_server_address(address: tuple):
    global server_ip, server_port, server_address
    server_ip, server_port = address
    server_address = address
    # print('Server address set to', address)


# Function to handle sending messages to the server
def transmit_messages():
    message_to_server(f'#JOIN_client_True_{CLIENT_IP}_{CLIENT_PORT}')

    while True:
        message = input('\rYou: ')
        # Send message
        if message[0] == '#':
            client_command(message)
        else:
            message_to_server(message)


# Sends a message to the server
# Need to add better handling for when the server isn't there to receive the message
def message_to_server(message):
    try:
        utility.tcp_transmit_message(message, server_address)
    except ConnectionRefusedError:
        print('Error sending message')


# Function to handle receiving messages from the server
def receive_messages():
    while True:
        client, address = client_socket.accept()
        data = client.recv(BUFFER_SIZE).decode().split('_')
        sender = data[0]
        message = data[1]
        if message[0] == '#':
            server_command(message)
        else:
            if sender == server_ip:
                print(f'\r{message}')
            else:
                print(f'\r{sender}: {message}')
            print('\rYou: ', end='')


# Handle commands entered by this client
def client_command(command):
    match command.split('_'):
        case ['#QUIT']:
            message_to_server(f'#QUIT_client_True_{CLIENT_IP}_{CLIENT_PORT}')
            sys.exit(0)


# Handle commands received by this client from the server
def server_command(command):
    match command.split('_'):
        case ['#QUIT']:
            print('\rGoodbye!')
            client_socket.close()
            sys.exit(0)


if __name__ == '__main__':
    main()
