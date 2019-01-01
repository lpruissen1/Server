# CS 472 - Homework 3 FTP Server
# Lee Pruissen
# server.py
# The entirety of my ftp server. Consists of main a main that spins off threads
# That executes individual FTP session with the server

# Import for communication
import socket

# Import for command line args
import sys

# Import for threading sessions
import threading

# Get datetime for logging
from datetime import datetime

# Import to change location in file system
import os

#Import for system information for SYST command
import platform

# Set passed in arguments
file = sys.argv[1]
port = 2001

#Set connetion modes
PASV = 0
PORT = 0

# Get local IP address
sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock1.connect(('8.8.8.8', 53))
host = (sock1.getsockname()[0])

print("HOST: " + host)

def configServer():
    f = open("server.conf", 'a')
    global PORT
    global PASV

    if 'port_mode = YES' in open('server.conf').read():
        PORT = 1
    if 'pasv_mode = YES' in open('server.conf').read():
        PASV = 1

    if((PASV + PORT) == 0):
        return 1


# Main of the server
# Creates a listening socket at the input port
# Creates thread once a client creates connection
def main():

    if(configServer()):
        print("Error in server.conf file")
        print("Can not create server")
        return 0
    # Create socket and have it listen

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('', port))
    sock.listen(0)

    print("Listening")

    # Listening loop
    while True:

        # Accept new connection
        conn, addr = sock.accept()

        # Start new thread running the ftpDriver(conn) function using the new connection
        t1 = threading.Thread(target=ftpDriver, args=(conn,))

        # Start thread
        t1.start()

        # Join the thread
        t1.join()

    # Close the listening socket
    sock.close()


# This is the function that is executed in a thread from the server
# It listens for new requests from the client and performs functions
# based on server state
# Parameter conn - control socket
def ftpDriver(conn):

    # The state of the current ftp session
    # 0 - Session active and waiting for login
    # 1 - Session active logged in
    # 2 - Session active and data connection open

    state = 0;

    # Session data socket
    data_sock = None;

    # Session connection message
    msg = "220 Connection created"
    sendRsp(conn, msg)

    # Enter login flow
    # State changes to 1 if correct credentials enterted
    state = loginFlow(conn)

    # While state is 0 keep attempting to login
    while (state == 0):
        state = loginFlow(conn)

    # Once logged in enter control flow
    while (state != -1):

        # Wait to receive request
        cmd, param = recvRqst(conn)

        # Clean inputs
        cmd = cmd.replace("\r\n", "")
        param = param.replace("\r\n", "")

        # If the client is requesting a data connection
        if (cmd == "PASV" or cmd == "PORT" or cmd == "EPRT" or cmd == "EPSV"):

            # Create data connection
            data_sock, state = dataConnection(conn, cmd, param)

        # If the client is requesting a data transfer
        elif ((cmd == "LIST" or cmd == "STOR" or cmd == "RETR") and (state == 2)):

            # Execute a data transfer and alter state
            state = dataCmd(cmd, param, data_sock, conn)

        # If client is sending control request
        elif (cmd == "CWD" or cmd == "CDUP" or cmd == "QUIT" or cmd == "HELP" or cmd == "SYST" or cmd == "PWD"):

            # Execute normal command and alter state
            state = normCmd(conn, cmd, param, state)

        # Else for an invalid command
        else:
            # Send response for an invalid command
            sendRsp(conn, "500 Invalid Command\r\n")

    return 0


# Executes function that needs a data connection
# Includes LIST, STOR, RETR
# Parameter input - name of command recieved
# Parameter param - possible filename
# Parameter dataConn - data socket
# Parameter comConn - communication socket
def dataCmd(input, param, dataConn, comConn):

    # if input cmd is LIST
    if (input == "LIST"):

        # Execute LIST function with data/com sockets
        list(dataConn, comConn)

        # Close the data socket
        dataConn.close()

        # Return logged in session state
        return 1

    # if input cmd is STOR
    if (input == "STOR"):

        # Execute the STOR command with data/com socket and filename
        stor(dataConn, comConn, param)

        # Close the data socket
        dataConn.close()

        # Return logged in session state
        return 1

    # if input cmd is RETR
    if (input == "RETR"):

        # Execute the RETR command with data/com socket and filename
        retr(dataConn, comConn, param)

        # Close the data socket
        dataConn.close()

        # Return logged in session state
        return 1

# Receives file over data connection and writes it to server specified by filename
# Parameter filename -  filename
# Parameter dataConn - data socket
# Parameter comConn - communication socket
def retr(dataConn, comConn, filename):

    # try/catch to check if file exists
    try:
        # Open file
        outFile = open(filename, "r")

        # Send response to send file
        msg = "150 data connection set and ready to receive data"
        sendRsp(comConn, msg)

    # if the file is not found
    except FileNotFoundError:

        # Send file not found response
        msg = "400 File not found"
        sendRsp(comConn, msg)

        # Exit function
        return 0

    # While a line exists send data to client over the data socket
    line = outFile.read(1024)
    while line:
        # Send file line to client
        sendData(dataConn, line)

        # Read another line
        line = outFile.read(1024)

    # close file
    outFile.close()

    # close data socket
    dataConn.close()

    # Log action
    log("File has been sent to client", 2)

    # Send transfer complete response
    msg = "226 Transfer Complete"
    sendRsp(comConn, msg)

    # Exit function
    return 0

# Sends file over data connection from server specified by filename
# Parameter filename -  filename
# Parameter dataConn - data socket
# Parameter comConn - communication socket
def stor(dataConn, comConn, filename):

    # Attempt to open/create file on server
    try:

        # Open file
        inFile = open(filename, "w")

        # Send message message ready to receive
        msg = "150 data connection set and ready receive data"
        sendRsp(comConn, msg)


    except FileNotFoundError:

        # Send file not found response
        msg = "400 File not found"
        sendRsp(comConn, msg)

        # Exit function
        return 0

    # loop until break
    while True:

        # Receive data from client
        data = recvData(dataConn)

        # If not data is received then break
        if not (data):
            break

        # Write line to file
        inFile.write(data)

    # Close data connection
    dataConn.close()

    # Send end of transfer response to client
    msg = "226 Transfer Complete"
    sendRsp(comConn, msg)

    # Exit function
    return 0

# Sends contents of current working directory over the data connection
# Parameter dataConn - data socket
# Parameter comConn - communication socket\
def list(dataConn, comConn):

    # Send ready to send data response
    msg = "150 data connection set and ready to send/recieve data"
    sendRsp(comConn, msg)

    # for line in current working directory send over data connection
    for f in os.listdir("./"):

        # Add a line break
        f = f + "\n"

        # Send listing
        sendData(dataConn, f)

    # Log action
    log("Directory Listing sent to client", 2)

    # Send end of transfer message
    msg = "226 Directory send OK"
    sendRsp(comConn, msg)

    # Exit function
    return 0

# Executes function that need strictly a communication socket
# Includes CWD, CDUP, QUIT, HELP, PWD, SYST
# Parameter conn - communication connection
# Parameter cmd - received command
# Parameter param - possible directory
# Parameter s - current state
def normCmd(conn, cmd, param, s):

    # trim input
    cmd = cmd.replace("\r\n", "")

    # If request is change working directory
    if (cmd == "CWD"):
        # Pass communication and directory
        cwd(conn, param)

    # If request is change directory up
    elif (cmd == "CDUP"):
        cdup(conn)

    # If request to quit
    elif (cmd == "QUIT"):
        return quit(conn)

    # If request of help
    elif (cmd== "HELP"):
        help(conn)

    # If request is pwd
    elif (cmd == "PWD"):
        pwd(conn)

    # If request is system info
    elif (cmd == "SYST"):
        syst(conn)

    return s

# Creates data connection
# Parameter conn - communication connection
# Parameter type - data connection type
# Parameter param - possible connection information
# Returns state change and data connection
def dataConnection(conn, type, param):

    if(PASV == 1):
        # If desired connection is PASV
        if (type == "PASV"):

            # Creates socket to listen
            data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            data_sock.bind((host, 0))
            data_sock.listen(1)

            try:
                # Get the port the socket is on
                data_port = data_sock.getsockname()[1]

                # format the host address
                newHost = host.replace('.', ',')

                # Format passive information
                p1 = data_port // 256
                p2 = data_port % 256

                # Format and passive message
                msg = "227 Entering Passive Mode (" + str(newHost) + "," + str(p1) + "," + str(p2) + ")"
                sendRsp(conn, msg)

                # Accept connection over listen socket
                conn1, addr = data_sock.accept()


            # Unknown host error
            except socket.gaierror as er:
                log("Unknown host during login", 0)

                # Create and send port response
                msg = ("425 Error creating data connection")
                sendRsp(conn, msg)

                # Return login state
                return 1

            # Socket timeout error
            except socket.timeout as er:
                log("Timeout error", 0)

                # Create and send port response
                msg = ("425 Error creating data connection")
                sendRsp(conn, msg)

                # Return login state
                return 1

            # return the connection and state change
            return conn1, 2

        # If desired connection is PASV
        if (type == "EPSV"):

            try:
                # Creates socket to listen
                data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                data_sock.bind((host, 0))
                data_sock.listen(1)

                # Gets data port socket is on
                data_port = data_sock.getsockname()[1]

                # Format and send extended passive message
                msg = "229 Entering Extended Passive Mode (|||" + str(data_port) + "|)"
                sendRsp(conn, msg)

                # accept connection over the listening socket
                conn1, addr = data_sock.accept()

            # Unknown host error
            except socket.gaierror as er:
                log("Unknown host during login", 0)

                # Create and send port response
                msg = ("425 Error creating data connection")
                sendRsp(conn, msg)

                # Return login state
                return 1

            # Socket timeout error
            except socket.timeout as er:
                log("Timeout error", 0)

                # Create and send port response
                msg = ("425 Error creating data connection")
                sendRsp(conn, msg)

                # Return login state
                return 1

            # return connection and state change
            return conn1, 2
    else:
        msg = ("501 PASV/EPSV mode is not active on the server")
        sendRsp(conn, msg)


    if (PORT == 1):
        # If desired connection is EPRT
        if (type == "EPRT"):

            # Parse port and host from response
            newport = param.split("|")[3]
            conhost = param.split("|")[2]

            # Create data connection
            try:
                data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                data_sock.connect((host, int(newport)))

                # Create and send EPRT response
                msg = ("200 EPRT connection created")
                sendRsp(conn, msg)

                # Log
                log("EPRT connection created", 2)

            # Unknown host error
            except socket.gaierror as er:
                log("Unknown host during login", 0)

                # Create and send port response
                msg = ("425 Error creating data connection")
                sendRsp(conn, msg)

                # Return login state
                return 1

            # Socket timeout error
            except socket.timeout as er:
                log("Timeout error", 0)

                # Create and send port response
                msg = ("425 Error creating data connection")
                sendRsp(conn, msg)

                # Return login state
                return 1

            # Return data socket and state change
            return data_sock, 2

        # If desired connection is PORT
        if (type == "PORT"):

            # Parse port from response
            value = param.split(",")
            newHost = value[0] + "." + value[1] + "." + value[2] + "." + value[3]
            newPort = int(value[4]) * 256 + int(value[5])

            # Create data connection
            try:
                data_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                data_sock.connect((newHost, int(newPort)))

                # Create and send port response
                msg = ("200 PORT connection created")
                sendRsp(conn, msg)

                # Log
                log("PORT connection created", 2)
            # Unknown host error
            except socket.gaierror as er:

                log("Unknown host during login", 0)

                # Create and send port response
                msg = ("425 Error creating data connection")
                sendRsp(conn, msg)

                # Return login state
                return 1

            # Socket timeout error
            except socket.timeout as er:
                log("Timeout error", 0)

                # Create and send port response
                msg = ("425 Error creating data connection")
                sendRsp(conn, msg)

                # Return login state
                return 1

            # return data connection and state change
            return data_sock, 2
    elif(type == "PORT" or type == "EPRT"):
        msg = ("501 PORT/EPRT mode is not active on the server")
        sendRsp(conn, msg)

    return None, 1

# Change working directory based on the arg
# Parameter conn - communication connection
# Parameter arg - directory
def cwd(conn, arg):

    # Attempt to change directory
    try:
        # Change current dir to passed input
        os.chdir(arg)

        # Create and send response
        msg = "250 Directory Change OK\r\n"
        sendRsp(conn, msg)

    # Set error response if failed
    except FileNotFoundError:
        msg = "504 The target directory does not exist\r\n"
        return 0

    sendRsp(conn, msg)
    return 0

# Move directory up one level
# Parameter conn - communication connection
def cdup(conn):

    # Attempt to move directory up one level
    try:
        os.chdir("..")
        msg = "200 Directory path moved up OK\r\n"

    # Set error message if failed
    except FileNotFoundError:
        msg = "500 Directory path not moved up\r\n"

    # Send cdup response based on outcome
    sendRsp(conn, msg)
    return 0

# Print working directory
# Parameter conn - communication connection
def pwd(conn):

    # Format and send pwd message
    path = "257 " + os.getcwd()
    sendRsp(conn, path)

# Exit the session
# Parameter conn - communication connection
def quit(conn):

    # Format and send exit message
    msg = "221 Goodbye!\r\n"
    sendRsp(conn, msg)
    conn.close()
    return -1


# Send sever help list over the communication connection
# Parameter conn - communication connection
def help(conn):

    # Send initial help message
    msg = "214-Help OK\r\n"
    sendRsp(conn, msg)

    # Send help message
    msg = "List of possible command on Lee's Server\r\n"
    msg = msg + " PWD SYST LIST CD CDUP EPSV PASV PORT EPRT RETR STOR QUIT\r\n"
    sendRsp(conn, msg)

    # Send end of help messsage
    msg = "214 Help OK.\r\n"
    sendRsp(conn, msg)

    # Exit function
    return 0

# send the system information through the communication connection
# Parameter conn - communication connection
def syst(conn):

    # Format and send system message
    msg = "215 " + str(platform.platform())
    sendRsp(conn, msg)

    # Exit function
    return 0

# Log file function
# Takes in the message and the type of message
def log(msg, flag):

    # Trim message
    msg = msg.replace("\r\n", "")

    # Open the log file to append
    f = open(file, 'a')

    # Datetime string
    dt = str(datetime.now())

    # Log the message as reciveved
    if (flag == 0):
        msg = dt + " " + "RECIEVED: " + msg + '\n'
        f.write(msg)

    # Log the message as sent
    elif (flag == 1):
        msg = dt + " " + "SENT: " + msg + '\n'
        f.write(msg)

    # Log the message as system message
    else:
        f.write(dt + " " + msg + '\n')

# Parameter conn - communication connection
def loginFlow(conn):

    # Open acct file
    acctF = open("acct.txt", 'r')

    # Recieve first msg to login
    cmd, param = recvRqst(conn)

    # If help dispaly help message
    if (cmd == "HELP"):
        help(conn)
        return 0

    # If quit then exit the session
    if (cmd == "QUIT"):
        return quit(conn)

    # If anything but user send the not logged in response
    if not (cmd == "USER"):
        # Else return error code
        msg = "530 Not logged in\r\n"
        sendRsp(conn, msg)
        return 0

    # Else ask for password
    else:
        # success
        msg = "331 Username OK, need password\r\n"
        user = param.replace("\r\n", "")
        sendRsp(conn, msg)

    # Recieve password
    cmd, param = recvRqst(conn)

    # If quit then quit
    if (cmd == "QUIT"):
        return quit(conn)

    # Give error response if request is not pass
    elif not (cmd == "PASS"):
        msg = "503 Need to login before any other command\r\n"

    # format password
    else:
        password = param.replace("\r\n", "");

    # Search account file for passed in credentials
    for line in acctF:
        line = line.split(" ")

        # Check correct  user+pass combo
        if (line[0].replace("\n", "") == user and line[1].replace("\n", "") == password):
            # Send succesful login message
            msg = "230 Succesful Login"
            sendRsp(conn, msg)

            # if ok return successful login and 1
            return 1

    # Else return message for failed login attempt
    msg = "430 Invalid username or password"
    sendRsp(conn, msg)

    # Bad login
    return 0

# Sends response over any connection given a socket and a message
def sendRsp(conn, msg):

    # Log the message sent
    log(msg, 1)

    # Encode and send message
    msg = msg.encode("utf-8")
    conn.sendall(msg)

def sendData(conn, msg):
    msg = msg.encode("utf=8")
    conn.sendall(msg)

# Recieves request over communication socket
def recvRqst(conn):

    # Gets request
    msg = recvData(conn)

    # Parse request if paramter is sent
    if (' ' in msg):
        cmd, param = msg.split(" ")

    # Else set whole message as whole command and param as nothing
    else:
        cmd = msg
        param = ""

    # Log message
    log(msg, 0)

    # Return command and parameter
    return (cmd, param)

# Received data from client over a socket
def recvData(conn):

    # Get message and decode
    msg = conn.recv(1024).decode("utf-8")

    # Return message
    return msg

# Run this bad boy
main()