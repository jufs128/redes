#!/usr/bin/python3

import sys
import socket
import select

PCKG_MAX_SIZE = 1000
WINDOW_SIZE = 5

#If execution was wrong
def usage():
    print("usage: ./cliente.py [IP] [PORT] [ARCHIVE]")
    print("example: ./cliente.py ::1 51511 archive.txt")

#Checks if character is ASCII
def is_valid_character(c):
    if ((c >= '0' and c <= '9') or (c >= 'A' and c <= 'Z') or (c >= 'a' and c <= 'z')
        or (c in " ,.?!:;+-*/=@#$%()[]{}")):
        return True
    else:
        return False

def archive_valid(name):
    if len(name) > 15: #Checks size of name
        return False

    count_dots = 0 #Counts dots
    count_format = 0 #Checks lenght of archive format (must be 3)
    for c in name:
        if count_dots == 1: #If after dot
            count_format += 1 #Counts a letter of the format
        if c == '.':
            count_dots += 1 #A dot was found
        #If character isn't valid, more than 1 dot or format bigger than 3
        if (is_valid_character(c) == False) or (count_dots > 1) or (count_format > 3):
            return False
    
    #If no dots or format smaller than 3
    if (count_dots == 0) or (count_format < 3):
        return False
    
    return True

#Returns list with packages from the file content
def divide_in_packages(file_content):
    pckg_list = []
    remaining = len(file_content) #Size of remaining text
    i = 0

    while remaining > PCKG_MAX_SIZE: #While remaining is bigger than package size
        pckg = file_content[i*PCKG_MAX_SIZE:(i+1)*PCKG_MAX_SIZE] #Selects next package (iteration x package size to iteration+1 x package size)
        msg_6 = PCKG_MAX_SIZE.to_bytes(2, 'big') + (bytearray(pckg, 'utf-8')) #Turns size and text to bytes
        pckg_list.append(msg_6)
        i += 1
        remaining -= PCKG_MAX_SIZE
    
    pckg = file_content[i*PCKG_MAX_SIZE:] #Remaining text is next package
    msg_6 = remaining.to_bytes(2, 'big') + (bytearray(pckg, 'utf-8'))
    pckg_list.append(msg_6)

    return pckg_list

#Sends packages in sliding window
def send_window(window, bool_pckg, udp_sock, type_addr):
    msg_type = 6 #Message type is 6 (FILE)
    for num_seq in range(len(bool_pckg)): 
        if bool_pckg[num_seq] == False: #If hasn't received ACK yet
            #Puts 6 and sequence number before size and package
            msg = msg_type.to_bytes(2, 'big') + num_seq.to_bytes(4, 'big') + window[num_seq]
            udp_sock.sendto(msg, type_addr) #Sends via UDP

#Checks number of times a package was retransmitted
def check_retransmission(window_index, retransmission_pckg, bool_pckg):
    end_i = min(window_index+WINDOW_SIZE, len(bool_pckg)) #If window is bigger than what's left of the list
    for i in range(window_index, end_i):
        if bool_pckg[i] == False:
            retransmission_pckg[i] += 1
            if retransmission_pckg[i] > 5: #If retransmitted 5 times
                return -1 #Disconnect
    return 0

#Sends the file to the server
def send_file(udp_sock, tcp_sock, type_addr, file_content):
    seq_pckg = divide_in_packages(file_content) #Gets list of packages (file content divided)
    bool_pckg = [] #Lists of if ACK was received for package
    retransmission_pckg = [] #List of number of times package was retransmitted
    for i in range(len(seq_pckg)): 
        bool_pckg.append(False) #Initially no ACK was received
        retransmission_pckg.append(0) #Initially no package was retransmitted
    
    i = 0 #Index of where window starts in seq_pckg
    while False in bool_pckg: #While some packages haven't received ACK

        end_i = min(i+WINDOW_SIZE, len(seq_pckg))
        window = seq_pckg[i:end_i] #Selects window
        bool = bool_pckg[i:end_i] #Selects booleans of ACK
        send_window(window, bool, udp_sock, type_addr) #Sends the window

        while False in bool: #While there are still False booleans for the window
            ack = select.select([tcp_sock], [], [], 1) #Selects input with timeout of 1 second
            if ack[0]: #If there was input
                data = tcp_sock.recv(6) #Process ACK (Turn its message boolean to True)
                if len(data) == 0: #If empty, server has disconnected
                    return -1

                if int.from_bytes(data[:2], 'big') == 5: #If received a FIM message here
                    print("Succeeded in sending file")
                    return 0 #Returns so sockets are closed
                elif int.from_bytes(data[:2], 'big') != 7:
                    return -1

                num_seq = int.from_bytes(data[2:], 'big')
                bool[num_seq] = True
            else: #If no activity in 1 second
                print("Timeout") #Print timeout
                break #Stop waiting
            
        bool_pckg[i:i+len(bool)] = bool #Update booleans on full package list

        if check_retransmission(i, retransmission_pckg, bool_pckg) == -1:
            return -1

        for value in bool: #Find first False value so it'll be resent
            if value == True: 
                i += 1 
            else: 
                break 
    
    #Receive FIM message to close TCP socket
    data = tcp_sock.recv(4)
    if len(data) == 0: #If empty, server has disconnected
        return -1

    if int.from_bytes(data[:2], 'big') == 5:
        print("Succeeded in sending file")
        return 0 #Returns so sockets are closed
    else:
        return -1

def main(args):
    #If the three required parameters weren't passed (or more than three)
    if len(args) != 4:
        usage()
        return
    
    HOST = args[1]
    PORT = int(args[2])
    ARCHIVE = args[3]

    #Check if archive name is valid
    if archive_valid(ARCHIVE) == False:
        print("Nome não permitido")
        return
    
    #Open and read file
    try:
        f = open(ARCHIVE, 'r')
    except: #Couldn't open archive
        print("Error; Couldn't open file")
        return
    file_content = f.read()
    file_size = len(file_content)
    f.close() #Close file

    #Connect via TCP (identifies IP type first)
    #type_addr lenght is 2 for IPv4 and 4 for IPv6
    type_addr = socket.getaddrinfo(HOST, PORT, 0, 0, socket.IPPROTO_TCP)[0][4]
    if len(type_addr) == 2:
        client=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    else:
        client=socket.socket(socket.AF_INET6, socket.SOCK_STREAM)

    #Connects to server (TCP)
    client.connect(type_addr)

    #Sends HELLO
    msg = 1
    client.sendall(msg.to_bytes(2, 'big'))
    
    #Receives CONNECTION
    data = client.recv(6)
    if len(data) == 0: #If empty, server has disconnected
        print("Error; Disconnected from server")
        client.close()
        return
    elif int.from_bytes(data[0:2], 'big') == 2:
        UDP_PORT = int.from_bytes(data[2:], 'big') #Identifies UDP port to connect
    else:
        client.close()
        return

    #Sends INFO FILE
    msg = 3
    msg_3 = msg.to_bytes(2, 'big') + (bytearray(ARCHIVE, 'utf-8')) + file_size.to_bytes(8, 'big')
    client.sendall(msg_3)

    #Receives OK
    data = client.recv(2)
    if len(data) == 0: #If empty, server has disconnected
        print("Error; Disconnected from server")
        client.close()
        return
    elif int.from_bytes(data, 'big') != 4: 
        client.close()
        return

    #Connect via UDP (identifies IP type first)
    #type_addr lenght 2 for IPv4 and 4 for IPv6
    type_addr = socket.getaddrinfo(HOST, UDP_PORT, 0, 0, socket.IPPROTO_UDP)[0][4]
    if len(type_addr) == 2:
        udp_client=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    else:
        udp_client=socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    
    #Sends file in packages
    if send_file(udp_client, client, type_addr, file_content) == -1:
        print("Error; Disconnected from server")

    #Close sockets
    udp_client.close()
    client.close()
    return


if __name__ == '__main__':
    sys.exit(main(sys.argv))