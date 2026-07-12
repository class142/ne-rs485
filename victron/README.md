Readme · MD
# dbus-ne355 — NordElettronica NE355 → Victron Venus OS
 
A Venus OS D-Bus service that reads a **NordElettronica NE355** RV control panel over
RS-485 and publishes its sensors as native Victron devices, so tanks, batteries and
switches render correctly in the Venus OS GUI and on VRM.
 
> Tested on a Raspberry Pi 2 running Venus OS v3.75. RS-485 at **38400 8N1**.

⚠️ Sending is not working yet! ⚠️
 
---
 
## What it exposes
 
The panel data is split across **five separate D-Bus services** (one process, one main
loop). Splitting is deliberate: Venus renders a device by matching its *service class*
and the standard paths for that class, so a tank cannot live under a battery service.
 
| Service | Class | DeviceInstance | Reports |
|---|---|---|---|
| `com.victronenergy.tank.ne355_fresh` | tank | 0 | Fresh-water level (`/Level`, `/Capacity`, `/Remaining`) |
| `com.victronenergy.tank.ne355_waste` | tank | 1 | Grey/waste level (binary full/empty) |
| `com.victronenergy.battery.ne355_car` | battery | 20 | Starter/vehicle battery voltage |
| `com.victronenergy.battery.ne355_house` | battery | 21 | Service/auxiliary battery voltage |
| `com.victronenergy.switch.ne355` | switch | 30 | Interior light, exterior light, water pump (read + control) |
 
Lights and the pump are **controllable** from the GUI when TX is wired to the bus (see
[Controlling outputs](#controlling-outputs)).
 
---
 
## Requirements
 
- A GX device / Raspberry Pi running **Venus OS** with root access.
- A USB-RS485 (or HAT) adapter with **automatic DE/RE** direction control. Reception
  working does **not** prove transmission works; manual-RTS adapters need extra handling.
- Wiring to the NE355 RS-485 bus: **A/B** (data pair) and **GND**.
- `velib_python` (ships with Venus at
  `/opt/victronenergy/dbus-systemcalc-py/ext/velib_python`) and Python 3 with `pyserial`.
---
 
## Adjust udev rule
 
The driver reads from a stable device node `/dev/ttyNE355`. A udev rule both creates that
symlink **and** tells Venus's `serial-starter` to leave the adapter alone (otherwise Venus
keeps opening the port to probe for VE.Direct/GPS/etc. and fights you for the bus).
 
You need your adapter's USB **vendor id**, **product id** and (ideally) **serial**.

### Run `dmesg | grep usb`
Example output:

    [  641.419437] usb 1-1.5: new full-speed USB device number 12 using dwc_otg
    [  641.587193] usb 1-1.5: New USB device found, idVendor=0403, idProduct=6001, bcdDevice= 6.00
    [  641.596083] usb 1-1.5: New USB device strings: Mfr=1, Product=2, SerialNumber=3
    [  641.603594] usb 1-1.5: Product: FT232R USB UART
    [  641.608288] usb 1-1.5: Manufacturer: FTDI
    [  641.612409] usb 1-1.5: SerialNumber: AG0JNN11
    [  641.635698] usb 1-1.5: Detected FT232RL
    [  641.642607] usb 1-1.5: FTDI USB Serial Device converter now attached to ttyUSB0
 
### Run `lsusb`
Example output:
 
_Bus 001 Device 012: ID 0403:6001 FTDI FT232R USB UART_
 
### Run `udevadm info` (try different ttyUSB devices)
 
`udevadm info -a -n /dev/ttyUSB0 | grep -E 'idVendor|idProduct|serial'`
 
Example output:
 
    SUBSYSTEMS=="usb-serial"
    ATTRS{idProduct}=="6001"
    ATTRS{idVendor}=="0403"
    ATTRS{serial}=="AG0JNN11"
    ATTRS{idProduct}=="9514"
    ATTRS{idVendor}=="0424"
    ATTRS{idProduct}=="0002"
    ATTRS{idVendor}=="1d6b"
    ATTRS{serial}=="3f980000.usb"
 
### Rule file: `z99-ignore-ne355.rules`
 
Edit the ids/serial to match your adapter:
 
```udev
# NE355 RS-485 adapter: keep serial-starter off it and give it a stable name.
ACTION=="add", SUBSYSTEM=="tty", \
  ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6001", ATTRS{serial}=="AG0JNN11", \
  ENV{VE_SERVICE}="ignore", SYMLINK+="ttyNE355"
```
 
- `ENV{VE_SERVICE}="ignore"` is what stops serial-starter from claiming the port.
- `SYMLINK+="ttyNE355"` gives the fixed `/dev/ttyNE355` the driver opens.
- If your adapter has **no unique serial** (many CH340 clones), drop the `serial` match
  and pin the physical USB port instead, e.g. add `KERNELS=="1-1.2"` (find yours with
  `udevadm info -a -n /dev/ttyUSB0 | grep KERNELS | head -1`).
## Add udev rule
 
```sh
mkdir -p /data/etc/udev/rules.d/
cp z99-ignore-ne355.rules /data/etc/udev/rules.d/
ln -sf /data/etc/udev/rules.d/z99-ignore-ne355.rules /etc/udev/rules.d/
udevadm control --reload-rules
udevadm trigger
```
 
Confirm the node exists and points at your adapter:
 
```sh
ls -l /dev/ttyNE355
```
 
> **USB devices trigger serial-starter via udev, so a rules reload alone is sometimes not
> enough.** If the symlink doesn't appear, replug the adapter or reboot.
 
## Install dbus service
 
```sh
mkdir -p /opt/victronenergy/dbus-ne355
cp dbus-ne355-driver.py /opt/victronenergy/dbus-ne355/
cp run /opt/victronenergy/dbus-ne355/
chmod +x /opt/victronenergy/dbus-ne355/run
ln -s /opt/victronenergy/dbus-ne355 /service/dbus-ne355
svc -u /service/dbus-ne355
svstat /service/dbus-ne355
```
 
### `run` script
 
Daemontools supervises the service and restarts it if it exits. The wait loop avoids a
restart storm before the tty appears at boot:
 
```sh
#!/bin/sh
exec 2>&1
while [ ! -e /dev/ttyNE355 ]; do sleep 1; done
exec python3 /opt/victronenergy/dbus-ne355/dbus-ne355-driver.py
```
 
### Managing the service
 
```sh
svstat /service/dbus-ne355          # status + uptime (rising uptime = stable)
svc -d /service/dbus-ne355          # stop
svc -u /service/dbus-ne355          # start
tail -F /var/log/dbus-ne355/current # logs (if a log/ service is configured)
```
 
### Surviving firmware updates
 
`/service/*` and `/etc/udev/rules.d/*` live on the read-only root and are wiped by a Venus
update; only `/data` persists. Recreate the symlinks at boot by adding them to
`/data/rc.local` (created if missing, `chmod +x`):
 
```sh
#!/bin/sh
ln -sf /data/etc/udev/rules.d/z99-ignore-ne355.rules /etc/udev/rules.d/
ln -sf /opt/victronenergy/dbus-ne355 /service/dbus-ne355
```
 
(Keep a copy of `dbus-ne355/` under `/data` too if you want it to survive updates.)
 
---
 
## Configuration
 
All knobs are constants at the top of `dbus-ne355-driver.py`:
 
| Constant | Purpose |
|---|---|
| `SERIAL_PORT`, `BAUD` | Device node and line speed (`/dev/ttyNE355`, 38400). |
| `FRESH_CAPACITY_L`, `WASTE_CAPACITY_L` | Real tank sizes in litres (drive `/Remaining`). |
| `*_BYTE`, `SYNC0/1`, `FRAME_LEN` | Frame offsets — verify against `/Debug/LastMessage`. |
| `TANK_MAP` | Fresh-tank rod encoding (see below). |
| `VALIDATE_CHECKSUM`, `GATE_BYTE` | Frame-validity gates. |
| `SEND_INIT`, `SEND_KEEPALIVE` | TX / bus-master behaviour. |
| `PRESS_FRAMES`, `PRESS_INTERVAL_MS` | How long a button press is held. |
 
### Controlling outputs
 
Toggling a switch in the GUI sends the matching command frame on the bus. Two things make
this actually work on the hardware:
 
- **A press is a toggle, not a set.** The driver compares the desired state to the last
  state read from the bus and only presses when they differ.
- **A single frame is ignored** — the unit only registers a press seen on **≥2 consecutive
  polls**, so each press is *held* for `PRESS_FRAMES` frames.
If your USB-RS485 adapter is manual-direction (drives DE/RE from RTS), presses will go
nowhere even though reception works — use an auto-direction adapter.
 
### Bus master vs. passive listener
 
The full status frame (with tank data) is only emitted when the master **alternates two
idle polls**. If the original NE panel is still on the bus it does this for you and the Pi
can stay a passive listener (`SEND_KEEPALIVE = False`). If you removed the panel and the Pi
is the **only** master, set `SEND_KEEPALIVE = True`; the driver then replicates the
alternation (`FF000000FF` dominant, `FF4000003F` every ~16th poll) at ~100 ms.
 
---
 
## Verify on the CLI
 
```sh
dbus -y                                                         # list all services
dbus -y com.victronenergy.tank.ne355_fresh /Level GetValue
dbus -y com.victronenergy.battery.ne355_house /Dc/0/Voltage GetValue
dbus -y com.victronenergy.switch.ne355 /Debug/LastMessage GetValue   # raw 20-byte frame
dbus -y com.victronenergy.switch.ne355 /SwitchableOutput/pump/State SetValue 1  # test TX
```
 
`/Debug/LastMessage` prints the last accepted frame as hex — the fastest way to re-check
offsets after any wiring or model change.
 
---
