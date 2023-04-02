import socket
import time
import logging
import json
from flask import Flask

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

#define global variables
ALLOFIT = b''

def hexToString(hex):
    return ''.join(format(x, '02x') for x in hex)

def sendAndWait(string):
    logging.info("Sending: %s", hexToString(string))
    s.send(string)
    time.sleep(0.1)
    return waitForResponse()

def waitForResponse():
    data = s.recv(1)
    count = 1

    stop = False
    while not stop:
        newdata = s.recv(1)
        data += newdata
        count += 1
        if len(data) >= BUFFER_SIZE:
            stringdata = hexToString(data)
            stop = True
        

    logging.info("Received: %s", stringdata)
    #hexdata = ''.join(format(x, '02x') for x in data)
    strcmd = stringdata[4:10]
    logging.debug("strcmd: %s", strcmd)
    strdata = stringdata[10:-2]
    logging.debug("strdata: %s", strdata)
    checksum = stringdata[-2:]
    #debug("checksum hex:", checksum)
    logging.debug("checksum recv int: %i", int(checksum, 16))
    logging.debug("checksum calc int: %i", calcChecksum(strdata))
    checksumCorrect = int(checksum, 16) == calcChecksum(strdata)
    logging.debug("checksum correct: %s", ("Yes" if checksumCorrect else "No"))
    return checksumCorrect

def calcChecksum(string):
    checksum = 0
    for i in range(0, len(string), 2):
        checksum += int(string[i:i+2], 16)
    checksum = checksum % 128
    return checksum

def calcChecksumTailing(string):
    checksum = 0
    for i in range(0, len(string) - 2, 2):
        checksum += int(string[i:i+2], 16)
    checksum = checksum % 128
    return checksum == int(string[-2:], 16)

def listen():
    global ALLOFIT
    data = s.recv(1)
    timeout = 10*BUFFER_SIZE
    count = 0
    stop = False
    while not stop:
        newdata = s.recv(1)
        count += 1
        data += newdata
        ALLOFIT += newdata
        if len(data) >= BUFFER_SIZE:
            data = data[1:BUFFER_SIZE]
            data += newdata
            
            stringdata = hexToString(data)
            checksum  = stringdata[-2:]
            calcedChecksum = calcChecksum(stringdata[0:-2])
            if int(checksum, 16)-2 == calcedChecksum:	
                strcmd = stringdata[0:10]
                logging.info("Received: %s", stringdata)
                data = b''
                count = 0
            else:
                logging.debug("Checksum error, shifting: %s, (%i vs %i)", stringdata, int(checksum, 16), calcedChecksum)
                
        if count > timeout:
            logging.info("No message found, payload %s",  hexToString(data))
            s.close()
            logging.info("Received: %s", hexToString(ALLOFIT))
            quit()

def getInfo():
    global ALLOFIT
    data = s.recv(1)
    timeout = 10*BUFFER_SIZE
    count = 0
    stop = False
    while not stop:
        newdata = s.recv(1)
        count += 1
        data += newdata
        ALLOFIT += newdata
        if len(data) >= BUFFER_SIZE:
            data = data[1:BUFFER_SIZE]
            data += newdata
            
            stringdata = hexToString(data)
            checksum  = stringdata[-2:]
            calcedChecksum = calcChecksum(stringdata[0:-2])
            if stringdata[0:2] == "ff" and (int(checksum, 16)%128)-2 == calcedChecksum:	
                return formatData(stringdata)
            else:
                logging.debug("Checksum error, shifting: %s, (%i vs %i)", stringdata, int(checksum, 16), calcedChecksum)
                
        if count > timeout:
            return json.dumps({'error': 'No message found', 'payload': hexToString(data), 'count': count})
        
def formatData(data):
    strcmd = data[0:10]
    return json.dumps({'cmd': strcmd,
                       'freshwater': getWatertankLevel(data[11:12]),
                        'greywater': getWatertankLevel(data[13:14]),
                        'greywater2': getWatertankLevel(data[15:16]),
                        'battery': getBatteryLevel(data[24:26]),
                        'battery2': getBatteryLevel(data[26:28]),
                        'pump': getPumpState(data[31:32]),
                        'indoorLight': getIndoorLightState(data[31:32]),
                        'outdoorLight': getOutdoorLightState(data[31:32]),
                          'data': data})

def getWatertankLevel(wtb):
    #decode bitmasked data (1=1/3, 2=2/3, 4=3/3)
    level = 0
    if int(wtb, 16) & 1:
        level += 1
    if int(wtb, 16) & 2:
        level += 1
    if int(wtb, 16) & 4:
        level += 1
    return level

def getBatteryLevel(data):
    return (int(data, 16)-30)/10

def getPumpState(data):
    return 1 if int(data, 16) & 4 else 0

def getIndoorLightState(data):
    return 1 if int(data, 16) & 1 else 0

def getOutdoorLightState(data):
    return 1 if int(data, 16) & 2 else 0


""" def readBuffer(s):
    try:
        data = s.read(1)
        n = s.inWaiting()
        if n:
            data = data + s.read(n)
        return data
    except Exception as e:
        print(e)
        quit() """

def reconnect():
    global ssend
    global s
    time.sleep(0.5)
    ssend.close()
    s.close()
    #ssend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #ssend.connect((TCP_IP, TCP_PORT))
    time.sleep(0.1)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((TCP_IP, TCP_PORT))
    time.sleep(0.5)


# Prepare 3-byte control message for transmission
TCP_IP = '192.168.1.1'
TCP_PORT = 44485
BUFFER_SIZE = 20

FULLOUT = b'\xff\x02\x00\xc0\xc1'
FULLOUT = b'\xff\x02\x00\xc0\xc1'
FULLIN = b'\xff\x01\x00\xc0\xc0'
FULLPUMP = b'\xff\x04\x00\xc0\xc3'

FULLINIT = b'\xff\x00\x00\x00\xFF'

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ssend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

reconnect()


app = Flask(__name__)
@app.route('/')
def index():
    global ssend
    global s
    reconnect()
    s.send(FULLINIT)
    reconnect()
    time.sleep(0.5)
    return getInfo()

@app.route('/pump')
def pump():
    global ssend
    global s
    reconnect()
    s.send(FULLINIT)
    reconnect()
    s.send(FULLPUMP)
    reconnect()
    time.sleep(0.5)
    return getInfo()

@app.route('/in')
def inlight():
    global ssend
    global s
    reconnect()
    s.send(FULLINIT)
    reconnect()
    s.send(FULLIN)
    reconnect()
    time.sleep(0.5)
    return getInfo()

@app.route('/out')
def outlight():
    global ssend
    global s
    reconnect()
    s.send(FULLINIT)
    reconnect()
    s.send(FULLOUT)
    reconnect()
    time.sleep(0.5)
    return getInfo()


try:
    app.run()
except KeyboardInterrupt:
    logging.info("Closing socket")
    s.close()
    ssend.close()
    logging.info("Received: %s", hexToString(ALLOFIT))
    quit()


