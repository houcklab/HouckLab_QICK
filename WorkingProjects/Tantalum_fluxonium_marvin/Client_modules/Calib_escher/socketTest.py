# import socket
#
# # Escher is 192.168.1.123, this is actually escher-pc
# # BF2 measurement computer 192.168.1.149 this is actually Marvin
#
# HOST = 'escher-pc'
# PORT = 4000
#
# with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#     s.bind((HOST, PORT))
#     s.listen()
#     conn, addr = s.accept()
#     with conn:
#         print(f"Connected by {addr}")
#         while True:
#             data = conn.recv(1024)
#             if not data:
#                 break
#             print(data)
#             #conn.sendall(data)


# echo-client.py

import socket
import time

HOST = "Marvin"  # The server's hostname or IP address
PORT = 4000  # The port used by the server

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    # s.sendall(b"Hello, world")
    # time.sleep(20)
    s.sendall('456.1213e'.encode())
    data = s.recv(1024)

print(f"Received {data!r}")