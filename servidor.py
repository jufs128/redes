#!/usr/bin/python3
#Allows execute as ./server.py

import sys
import select
import socket
import os.path
import errno

save_path = 'output/'

HOST = '::'
PORT = 0 #Will be received from command line
UDP_PORT = 1 #Starts as PORT + 1; incremented as port is used

PCKG_MAX_SIZE = 1000
WINDOW_SIZE = 5

#Input channels for select
inputs = []
#Output channels for select
outputs = []
# Outgoing message queues (socket:list)
message_queues = {}

#Current UDP ports open (data structure list)
udp_clients = []
#UDP socket list
udp_sockets = []

#Client's data structure
class UDP_client:
    def __init__(self, t_sock, u_port, u_sock) -> None:
        self.tcp_sock = t_sock #TCP socket
        self.udp_port = u_port #UDP port
        self.udp_sock = u_sock #UDP socket

        self.file_name = '' #Saved file name
        self.file_content = [] #List of file content
        self.window_begin = 0 #Beginning of window is initially the first package
    
    #Save file name and alocate space
    def file_properties(self, name, size):
        self.file_name = name
        num_pckg = (int) (size / PCKG_MAX_SIZE) #Number of 1000 bytes packages

        if (size % PCKG_MAX_SIZE) > 0: #Misssing any space
            num_pckg += 1 #Another space
        
        for i in range(num_pckg): #Initially None, as packages are received turns to string
            self.file_content.append(None)
    
    def insert_pckg(self, num_seq, msg): #Puts package in correct position
        self.file_content[self.window_begin + num_seq] = msg

    def update_window_beginning(self): #Updates the window beginning
        for i in range(len(self.file_content)):
            if self.file_content[i] == None: #First None is the new beginning
                self.window_begin = i
                break

def usage(): #Error in execution
    print("usage: ./servidor.py [PORT]")
    print("example: ./servidor.py 51511")

#Processing HELLO message
def msg_1(c_socket):
    global UDP_PORT
    c_udp = UDP_PORT
    UDP_PORT += 1 #Port now used, increment 1

    #Opens UDP socket for connection
    tuple_addr = socket.getaddrinfo(HOST, c_udp, 0, 0, socket.IPPROTO_UDP)[0][4]
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)

    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)

    sock.setblocking(0)
    sock.bind(tuple_addr)

    tcp_udp = UDP_client(c_socket, c_udp, sock)

    udp_clients.append(tcp_udp) #List of connecte clients data structure
    udp_sockets.append(sock) #List of UDP connected sockets
    inputs.append(sock) #Input list for select

    return tcp_udp.udp_port

#Finds the name and size of file in message
def find_file_name_size(msg):
    name = msg[:len(msg) - 8] #Until beginning of file size (8 bytes int)
    archive = name.decode('utf-8') #Decode file name
    
    size = int.from_bytes(msg[len(msg) - 8:], 'big') #Size is the rest of the string
    return archive,size

#Processing INFO FILE message
def msg_3(c_socket, msg):
    file_name, file_size = find_file_name_size(msg[2:])
    for conn in udp_clients: #Finds client's data structure
        if conn.tcp_sock == c_socket:
            c_data = conn
            break
    
    c_data.file_properties(file_name, file_size) #Prepares to receive file

#Processing FILE message
def msg_6(msg, udp_socket):
    for conn in udp_clients: #Finds client's data structure
        if conn.udp_sock == udp_socket:
            client = conn
            break
    
    pckg_num = int.from_bytes(msg[2:6], 'big') #Gets sequence number
    pckg_size = int.from_bytes(msg[6:8], 'big') #Gets size
    #If length of message is different than expected
    if len(msg[8:].decode('utf-8')) != pckg_size:
        return -1, client

    client.insert_pckg(pckg_num, msg[8:].decode('utf-8')) #Puts in the correct position of contents

    return pckg_num, client

def id_tcp_msg(msg, c_socket): #Identifies the messages received via TCP
    if int.from_bytes(msg[0:2], 'big') == 1: #Received HELLO
        port = msg_1(c_socket)
        answer = 2
        return answer.to_bytes(2, 'big') + port.to_bytes(4, 'big') #Sends CONNECTION

    elif int.from_bytes(msg[0:2], 'big') == 3: #Received INFO FILE
        msg_3(c_socket, msg)
        answer = 4
        return answer.to_bytes(2, 'big') #Sends OK

#Saves the file in "output" folder
def save_file(client):
    complete_name = os.path.join(save_path, client.file_name) #Diretory + file name

    if not os.path.exists(os.path.dirname(complete_name)): #If directory doesn't exist, creates one
        try: #Try for guarding against race conditions (directory was create between commands)
            os.makedirs(os.path.dirname(complete_name))
        except OSError as exec:
            if exec.errno != errno.EEXIST:
                raise
    
    f = open(complete_name, "w") #Creates file
    for pckg in client.file_content:
        f.write(pckg) #Writes packages received in file

    f.close() #Closes file

def main(args):
    #If the required parameter wasn't passed (or more than one)
    if len(args) != 2:
        usage()
        return

    #To change value in function
    global PORT
    global UDP_PORT

    #Gets command line port
    PORT = int(args[1])
    UDP_PORT = PORT + 1

    tuple_addr = socket.getaddrinfo(HOST, PORT, 0, 0, socket.IPPROTO_TCP)[0][4] #Gets address info for bind
    server = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)

    #Connects to both IPv4 and IPv6
    server.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)

    server.setblocking(0)

    server.bind(tuple_addr)
    server.listen()

    #To select connections to server, add its socket to inputs
    inputs.append(server)

    while inputs:
        readable, writable, exceptional = select.select(inputs, outputs, inputs)
        
        #Input
        for sockets in readable:
            #Data received on UDP
            if sockets in udp_sockets:
                window_msgs = []
                for i in range(WINDOW_SIZE): #Receives FILE messages in window
                    udp_socket = select.select([sockets], [], [], 0.2)
                    if udp_socket[0]: #If received before timeout
                        data_udp, caddr = sockets.recvfrom(1024)
                        window_msgs.append(data_udp)
                    else:
                        break
                
                #Processing and sending ACK for all received packages
                for data in window_msgs:
                    seq, client = msg_6(data, sockets)
                    if seq != -1:
                        msg = 7
                        answer = msg.to_bytes(2, 'big') + seq.to_bytes(4, 'big')
                        client.tcp_sock.send(answer) #Sends immediately instead of through select output because of timeout in client
                
                #If file content is complete
                if None not in client.file_content:
                    print('Finished receiving file from', client.tcp_sock.getpeername())
                    msg = 5 
                    save_file(client) #Save file
                    client.tcp_sock.send(msg.to_bytes(2, 'big')) #Send FIM
                    #Disconnects UDP socket
                    inputs.remove(sockets)
                    udp_sockets.remove(sockets)
                    sockets.close()
                else:
                    client.update_window_beginning()

            #Connection to server
            elif sockets == server:
                conn, caddr = server.accept()
                print('Connected by', caddr)
                conn.setblocking(0)
                inputs.append(conn)
                # Give the connection a queue for data we want to send
                message_queues[conn] = []

            #Data to be received
            else:
                data = sockets.recv(25)
                if data: #Data was received
                    message_queues[sockets].append(id_tcp_msg(data,sockets)) #Adds answer to its message queue
                    if sockets not in outputs:
                        outputs.append(sockets) #Puts socket in output list
                else: #Empty data
                    print('Closing connection to', sockets.getpeername())
                    #Disconnects
                    if sockets in outputs:
                        outputs.remove(sockets)
                    inputs.remove(sockets)
                    sockets.close()
                    del message_queues[sockets]
    
        #Output
        for sockets in writable:
            if sockets in message_queues:
                if len(message_queues[sockets]) == 0: #No message to be sent for the socket
                    outputs.remove(sockets)
                else:
                    next_msg = message_queues[sockets][0] #Gets next message
                    message_queues[sockets].remove(next_msg)
                    sockets.send(next_msg)

        #Except
        for sockets in exceptional: #Disconnects from socket
            inputs.remove(sockets)
            if sockets in outputs:
                outputs.remove(sockets)
            sockets.close()

            #Remove its message queue
            del message_queues[sockets]
    
    return


if __name__ == '__main__':
    sys.exit(main(sys.argv)) 