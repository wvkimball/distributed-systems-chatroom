#!/usr/bin/env python3.10
# Anything that would be repeated in both the server and the client code can/will go here
import socket

broadcast_port = 10002
buffer_size = 1024

# Random code to broadcast / listen for to filter out other network traffic
broadcast_code = '9310e231f20a07cb53d96b90a978163d'

# Random code to respond with
response_code = 'f56ddd73d577e38c45769dcd09dc9d99'


# source: https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP