## Webserver for Arduino
Tested on NodeMCU (ESP8266)

### Requirements
- RS485-to-UART converter (e.g. MAX485) with direct access to read/drive enable pins (can be connected to each other thus only using one GPIO pin)

| MAX485 pin | Arduino pin | GPIO pin (NodeMCU)    |
|------------|-------------|-------------|
| DE/RE      | D6          | 12          |
| RX         | D7          | 13          |
| TX         | D5          | 14          |

- WiFi device (like smartphone) to connect to the WiFiManager on IP 192.168.4.1 to configure the WiFi connection
- Ardiuno code at [ne334_ws_1/ne334_ws_1.ino](ne334_ws_1/ne334_ws_1.ino)