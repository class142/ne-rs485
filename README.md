## Description
Reverse engineering of the RS485 protocol used in the NordElettronica NE334 control panel for controlling the electronics main unit of the camper van.

More information about the data packet format can be found in the [spec.md](spec.md) file.

### Arduino example implementation for ESP8266
See [arduino/README.md](arduino/README.md) for more information.

### Python example implementation

For a reference implementation see the [flask_server.py](flask_server.py) file.
NOTE: This is a work in progress, not yet fully functional and a complete mess.

If you want to try it out anyway, change TCP_PORT and TCP_IP according to your Serial-to-TCP converter and run the flask_server.py file.
It will start a webserver on port 5000 and you can access the web interface at http://localhost:5000.

Available endpoints are:
| Endpoint | Description |
| --- | --- |
| / | data in JSON format |
| /pump |  switch pump on/off |
| /in |  switch indoor light on/off |
| /out |  switch outdoor light on/off |

## Disclaimer

All names, trademarks, and copyrights belong to the respective manufacturers.

This project has been created for demonstration purposes only, to show how the RS485 bus can be interfaced. The authors of this project do not claim any ownership over the names, trademarks, or copyrights of the respective manufacturers.