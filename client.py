import socket
import threading
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
        broadcast_socket.sendto(utility.BROADCAST_CODE.encode(), ('<broadcast>', utility_temp.BROADCAST_PORT))
        print("Looking for server")
        # Wait for a response packet. If no packet has been received in 2 seconds, sleep then broadcast again
        try:
            data, address = broadcast_socket.recvfrom(1024)
            if data.startswith((utility_temp.RESPONSE_CODE + '_' + CLIENT_IP).encode()):
                message = data.decode().split('_')
                print("Found server at", address[0])
                set_server_address((address[0], int(message[2])))
                break
        except TimeoutError:
            sleep(3)

    broadcast_socket.close()


def set_server_address(address: tuple):
    global server_ip, server_port, server_address
    server_ip, server_port = address
    server_address = address
    print('Server address set to', address)


# Function to handle sending messages to the server
def transmit_messages():
    utility_temp.transmit_message(f'#JOIN_{CLIENT_IP}_{CLIENT_PORT}', server_address)

    while True:
        message = input('\rYou: ')
        # Send message
        utility.transmit_message(message, server_address)


# Function to handle receiving messages from the server
def receive_messages():
    while True:
        client, address = client_socket.accept()
        data = client.recv(BUFFER_SIZE).decode().split('_')
        sender = data[0]
        message = data[1]
        print(f'\r{sender}: {message}\nYou: ', end='')


if __name__ == '__main__':
    main()
