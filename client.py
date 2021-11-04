import socket
import threading
import sys
from utility import BUFFER_SIZE
import utility
from time import sleep

# Constants
CLIENT_IP = utility.get_ip()

# Create TCP socket for listening
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client_socket.bind((CLIENT_IP, 0))
client_socket.listen()

# Find listening port
client_port = client_socket.getsockname()[1]

# Create global variables which will be set by server response
server_ip = ''
server_port = 0
server_address = (server_ip, server_port)


def main():
    utility.cls()
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
            if data.startswith(f'{utility.RESPONSE_CODE}_{CLIENT_IP}'.encode()):
                message = data.decode().split('_')
                print("Found server at", address[0])
                set_server_address((address[0], int(message[2])))
                break
        except TimeoutError:
            sleep(3)

    broadcast_socket.close()
    message_to_server(f'#JOIN_client_1_{CLIENT_IP}_{client_port}')


# Sets the server address which messages will be sent to
def set_server_address(address: tuple):
    global server_ip, server_port, server_address
    server_ip, server_port = address
    server_address = address
    # print(f'\rServer address set to {address}\nYou: ', end='')


# Function to handle sending messages to the server
def transmit_messages():
    while True:
        message = input('\rYou: ')
        # Send message
        if message[0] == '#':
            client_command(message)
        else:
            message_to_server(format_chat(message))


# Sends a message to the server
# If the server isn't there, the client starts searching again
def message_to_server(message):
    try:
        utility.tcp_transmit_message(message, server_address)
    except (ConnectionRefusedError, TimeoutError):
        print('\rError sending message, searching for server again')
        broadcast_for_server()


def format_chat(message):
    return f'#CHAT_{CLIENT_IP}_{client_port}_{message}'


# Function to handle receiving messages from the server
def receive_messages():
    while True:
        client, address = client_socket.accept()
        data = client.recv(BUFFER_SIZE).decode()
        if data[0] == '#':
            server_command(data)
        else:
            data = data.split('_')
            message = data[0]
            sender = data[1]
            if sender == server_ip:
                print(f'\r{message}')
            else:
                print(f'\r{sender}: {message}')
            print('\rYou: ', end='')


# Handle commands entered by this client
def client_command(command):
    match command.split('_'):
        case ['#QUIT']:
            message_to_server(f'#QUIT_client_1_{CLIENT_IP}_{client_port}')
            sys.exit(0)


# Handle commands received by this client from the server
def server_command(command):
    match command.split('_'):
        case ['#QUIT']:
            print('\rGoodbye!')
            client_socket.close()
            sys.exit(0)
        case ['#LEAD', ip, port]:
            set_server_address((ip, int(port)))


if __name__ == '__main__':
    main()
