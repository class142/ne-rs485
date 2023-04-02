# read string without 0x from stdin and calculate checksum
# usage: python calcChecksum.py <string>
# example: python calcChecksum.py 0x01 0x03 0x00 0x00 0x00 0x02
# output: 0x05

import sys

def calcChecksum(string):
    checksum = 0
    for i in range(0, len(string), 2):
        checksum += int(string[i:i+2], 16)
    checksum = checksum % 128
    return checksum

if __name__ == "__main__":
    string = sys.argv[1]
    checksum = calcChecksum(string)
    print ("0x%02x" % checksum)