# RS485 bus protocol of NordElettronica NE334

Example message:

| ff0000c0bf |0|7|1|0|0|0|1011|f3|00|a4|ac|ff|00010000|7b |
|------------|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Idle Command |0|Freshwater tank |1|Grey water tank 1 |0|Grey water tank 2 | ??? | ??? | Ignition? | Car battery | Auxillary battery | ??? | status flags | checksum |

## Available commands

Every unknown command can be used for waking up the bus.
You should send an init message before sending any other command to make sure the bus is awake, especially if the control panel is switched off.
The main unit will shut of after a couple of seconds if no command is sent. So you have to send idle commands yourself if the control panel is switched off.

Timing doesn't matter at all, just send the command whenever you want. For the idle command an interval of 5 seconds seems to be fine. You could wait for the main unit to stop sending its data before sending the next idle command, but that seems like too much effort. Although it might be necessary on future firmware versions.

| Command | Meaning | Notes |
| --- | --- | --- |
| FF400080BF | init? | |
| FF0000C0FF | init? | |
| FF4000C0BF | Idle | Sent as response by main unit |
| FF0100C0C0 | Indoor light 1 | Second circuit isn't used, maybe switched also |
| FF01000000 | All indoor lights | Apparently used for switching both light circuits, although only first is used |
| FF0200C0C1 | Outdoor light | |
| FF0400C0C3 | Water pump | |
| FF8000007F | All off | Switches off all lights and pump |

## Water tank bitmasks
To be valid, probes have to be summed up, so a full tank is 0x7 otherwise control panel shows `---` which doesn't matter if you don't tinker with the wiring and just want to read data.

| Bit | Probe |
| --- | --- |
| 0 | Empty |
| 1 | 1/3 |
| 2 | 2/3 |
| 3 | 3/3 |

## Unknown values
- 1011 always stays the same
- 0xf3 switches to 0xf4 sometimes (also if ignition is on --> something else)
- 0x00 changes to 0x80 if ignition is on, maybe Bitmask for car features received via CAN? not sure if main unit even has CAN...

## Battery values
Not really sure, the following values have been observed

| Volts | Value |
| --- | --- |
| 12.4 | 99 = 153 |
| 12.5 | 99 |
| 12.6 | 9a+9b |
| 12.7 | 9b+9c |
| 13.1 | a0 |
| 13.2 | a2 |
| 13.3 | a3 |
| 13.4 | a4 = 164 |
| 13,5 | a5+a6 |
| 13,6 | a6+a7 |
| 13,7 | a8 |
| 13,8 | a9 = 169 |
| 14,0 | ab+ac |

Can be approximated to 0.2V by:

`U = (int(value, 16)-30)/10 V`

## Status flags

| Flag | Meaning | Values | 
| --- | --- | --- |
| 1 | ? | ? |
| 2 | ? | 3? |
| 3 | ? | 6? |
| 4 | Active features | Bitmask: 1 = indoor light, 2 = outdoor light, 4 = water pump |
| 5 | ? | ? |
| 6 | Shore power | 1 = connected |
| 7 | ? | ? |
| 8 | ? | ? |

## Checksum

The checksum is calculated by adding all bytes except the last 4 (=2 Hex digits) and calculating `[sum] modulo 128 + 2`.
If you strip both 0xff or use RFC2217 instead of RAW TCP mode of RS485-TCP-Bridge, don't have to add 2 since `2*0xff = -2` for 2-complement hex digits.

## Hardware

### Devices used for testing
- Teltonika RUT955 with Digitus RS485-to-USB converter
- INSYS icom MRX5 LTE with SI MRcard's integrated RS485 

&#9432; used integrated RS485-to-TCP bridge on above devices

- Rigol DS1054Z Oscilloscope for probing