#include <ESP8266WiFi.h>
#include <WiFiClient.h>
#include <WiFiManager.h>  
#include <SoftwareSerial.h>

const int bufferLength = 20; // length of buffer to read
const int checksumLength = 2; // length of checksum in bytes
const int checksumMod = 128; // modulus for checksum calculation

int idleInterval = 5000;
int timerStart = 0;
bool needsIdle = true;

byte buffer[bufferLength]; // buffer to hold data read from serial
int bufferIndex = 0; // index of next byte to read into buffer
int bufferAllIndex = 0;
int bytesRead = 0; // number of bytes to read from serial
const int maxbytesRead = bufferLength*3; // maximum number of bytes to read from serial
byte bufferAll[maxbytesRead];
byte checksum = 0; // checksum of bytes in buffer
byte calcedChecksum = 0;
byte receivedChecksum = 0;
bool checksumMatch = false; // flag to indicate if checksum matches

int incoming = 0;
int incoming2 = 0;

const int DERE = D6;

char idle[] = {0xff, 0x40,0x00, 0x80, 0xbf};
char lightin[] = {0xff, 0x01, 0x00, 0xc0, 0xc0};
char lightout[] = {0xff, 0x02, 0x00, 0xc0, 0xc1};
char pump[] = {0xff, 0x04, 0x00, 0xc0, 0xc3};

WiFiServer server(80);

SoftwareSerial rs485(D7, D5);

void setup() {
  
  Serial.begin(38400);
  Serial.setDebugOutput(false);
  rs485.begin(38400);
  delay(1000);

  pinMode(DERE, OUTPUT);
  digitalWrite(DERE, LOW); //read mode


  //WiFi.mode(WIFI_AP_STA);
  WiFiManager wifiManager;
  delay(250);
  // Connect to Wi-Fi network
  bool res = wifiManager.autoConnect("NE-RS485-to-TCP bridge");
  
  if(!res) {
      Serial.println("Failed to connect");
      ESP.restart();
  } 
  else {
      //if you get here you have connected to the WiFi    
      Serial.println("Connected");
  }

  server.begin();
}

void loop() {

  if (needsIdle && millis() >= timerStart+idleInterval) {
    timerStart = millis();
    String data = fetchData();
    if (somethingOn(data)) {
      sendIdle();
    } else {
      needsIdle = false;
    }
  }
  
  WiFiClient client = server.available();   // listen for incoming clients

  if (client) {                             // if you get a client,
    Serial.println("New Client.");           // print a message out the serial port
    String currentLine = "";                // make a String to hold incoming data from the client
    while (client.connected()) {            // loop while the client's connected
      if (client.available()) {             // if there's bytes to read from the client,
        char c = client.read();             // read a byte, then
        Serial.write(c);                    // print it out the serial monitor
        if (c == '\n') {                    // if the byte is a newline character

          // if the current line is blank, you got two newline characters in a row.
          // that's the end of the client HTTP request, so send a response:
          if (currentLine.length() == 0) {
            // HTTP headers always start with a response code (e.g. HTTP/1.1 200 OK)
            // and a content-type so the client knows what's coming, then a blank line:
            String data = fetchData();
            if (data.equals("")) {
              client.println("HTTP/1.1 500 Internal Server Error");
            } else {
              client.println("HTTP/1.1 200 OK");
            }
            client.println("Content-type:application/json");
            client.println();

            // the content of the HTTP response follows the header:
            
            client.print(createJson(data));

            // The HTTP response ends with another blank line:
            client.println();
            // break out of the while loop:
            break;
          } else {    // if you got a newline, then clear currentLine:
            currentLine = "";
          }
        } else if (c != '\r') {  // if you got anything else but a carriage return character,
          currentLine += c;      // add it to the end of the currentLine
        }

        if (currentLine.endsWith("GET /p")) {
          Serial.println("Toggle pump");
          sendData(pump);
        } else if (currentLine.endsWith("GET /i")) {
          Serial.println("Toggle indoor light");
          sendData(lightin);
        } else if (currentLine.endsWith("GET /o")) {
          Serial.println("Toggle outdoor light");
          sendData(lightout);
        }
      }
    }
    // close the connection:
    client.stop();
    Serial.println("Client Disconnected.");
  }

  // read from serial until buffer is full or checksum matches
  /* String result = fetchData();
  if (result != "") {
    Serial.print("Message received: ");
    Serial.println(result);
    Serial.print("Converted: ");
    Serial.println(createJson(result));
  } else {
    Serial.println("No message received");
  }
  delay(1000); */
}

bool sendData(char* data) {
  preSend();
  rs485.write(data, 5);
  postSend();
  needsIdle = true;
  return true;
}

void sendIdle() {
  digitalWrite(DERE, HIGH);
  delay(10);
  rs485.write(idle, sizeof(idle));
  delay(100);
  digitalWrite(DERE, LOW);
}

void preSend() {
  sendIdle();
  delay(500);
  digitalWrite(DERE, HIGH);
  delay(10);
}

void postSend() {
  delay(100);  
  digitalWrite(DERE, LOW);  
}

String fetchData() {
  bufferIndex = 0;
  bufferAllIndex = 0;
  checksum = 0;
  checksumMatch = false;
  bytesRead = 0;

  for (int i = 0; i < bufferLength; i++) {
    buffer[i] = 0;
  }

  sendIdle();

  while (!checksumMatch) {
    if (rs485.available()) {
      // read the next byte and add it to the buffer
      byte nextByte = rs485.read();
      buffer[bufferIndex] = nextByte;
      bufferAll[bufferAllIndex] = nextByte;
      bufferAllIndex += 1;
      bytesRead += 1;
      bufferIndex++;
    }

    // if buffer is full and checksum doesn't match, shift the buffer and continue reading
    if (bufferIndex >= bufferLength) {
      calcedChecksum = 0;
      for (int i = 0; i < bufferLength-2; i++) {
        calcedChecksum += buffer[i];
      }
      calcedChecksum = calcedChecksum % checksumMod; // apply modulus
      receivedChecksum = ((buffer[bufferLength-2] << 8) | buffer[bufferLength-1]);
      receivedChecksum %= checksumMod;
      checksumMatch = (calcedChecksum == receivedChecksum-2);

      if (checksumMatch && buffer[0] == 255 && buffer[14] == 255) { // both have to be ff
        return toHexString(buffer, sizeof(buffer));
      } else {
        bufferIndex--;
        for (int i = 0; i < bufferLength-1; i++) {
          buffer[i] = buffer[i+1];
        }
      }
    }
    if (bytesRead >= maxbytesRead) {
      Serial.print("Timeout, read: ");
      Serial.println(toHexString(bufferAll, sizeof(bufferAll)));
      return "";
    }
  }
}

String toHexString(byte* hex, int length) {
  String hexString = "";
  String hexDigit = "";
  for (int i = 0; i < length; i++) {
    hexDigit = String(hex[i], HEX);
    if (hex[i]<10) {
      hexDigit = "0" + hexDigit;
    }
    hexString += hexDigit;
  }
  return hexString;
}

bool somethingOn(String data) {
  String subdata = data.substring(31, 32);
  bool pumpOn = getPumpState(subdata).equals("1");
  bool inLightOn = getIndoorLightState(subdata).equals("1");
  bool outLightOn = getOutdoorLightState(subdata).equals("1");
  return (pumpOn || inLightOn || outLightOn);
}

String createJson(String data) {
  if (data.equals("")) {
    return "{\"error\":\"Failed to find valid message\",\"rawdata\":\"" + toHexString(bufferAll, sizeof(bufferAll)) + "\"}";
  }
  return "{\"rawdata\":\"" + data + "\","
          "\"freshwater\":\"" + getWatertankLevel(data.substring(11, 12)) + "\","
          "\"greywater1\":\"" + getWatertankLevel(data.substring(13, 14)) + "\","
          "\"greywater2\":\"" + getWatertankLevel(data.substring(15, 16)) + "\","
          "\"indoorLight\":\"" + getIndoorLightState(data.substring(31, 32)) + "\","
          "\"outdoorLight\":\"" + getOutdoorLightState(data.substring(31, 32)) + "\","
          "\"pump\":\"" + getPumpState(data.substring(31, 32)) + "\","
          "\"battery1\":\"" + getBatteryLevel(data.substring(24, 26)) + "\","
          "\"battery2\":\"" + getBatteryLevel(data.substring(26, 28)) + "\"}"; 
} 

String getBatteryLevel(String data) {
  float encodedVoltage = stringToInt(data);
  float voltage = (encodedVoltage-30)/10;
  char strbuf[10];
  dtostrf(voltage, 0, 1, strbuf);
  return String(strbuf);
}

String getWatertankLevel(String wts) {
  int level = 0;
  int wti = stringToInt(wts);
  if (wti & 1) {
    level += 1;
  }
  if (wti & 2) {
    level += 1;
  }
  if (wti & 4) {
    level += 1;
  }
  return String(level, 10);
}

String getIndoorLightState(String data) {
  return stringToInt(data) & 1 ? "1" : "0";
}

String getOutdoorLightState(String data) {
  return stringToInt(data) & 2 ? "1" : "0";
}

String getPumpState(String data) {
  return stringToInt(data) & 4 ? "1" : "0";
}

int stringToInt(String s) {
  return (int) strtol(s.c_str(), NULL, 16);
}
