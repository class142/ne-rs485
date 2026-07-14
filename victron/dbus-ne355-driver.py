#!/usr/bin/env python3
"""
dbus-ne355 - NordElettronica NE355 RS-485 -> Victron Venus OS

Splits the panel data into separate Venus OS services so each device renders
correctly in the GUI:

    com.victronenergy.tank.ne355_fresh    -> fresh water tank
    com.victronenergy.tank.ne355_waste    -> grey/waste water tank
    com.victronenergy.battery.ne355_car   -> starter / vehicle battery (voltage only)
    com.victronenergy.battery.ne355_aux -> auxiliary / living battery (voltage only)
    com.victronenergy.switch.ne355        -> interior/exterior light + pump (toggle)

Each service gets its own /DeviceInstance. They all run in one process off one
GLib main loop; a single D-Bus connection can own multiple names.
"""

import os
import sys
import serial
import dbus
from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop

sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')
from vedbus import VeDbusService

# ----------------------------------------------------------------------------
# Configuration  -  adjust these to your rig
# ----------------------------------------------------------------------------
SERIAL_PORT = '/dev/ttyNE355'
BAUD        = 38400

# Real tank sizes in litres (used for /Capacity and /Remaining)
FRESH_CAPACITY_L = 100
WASTE_CAPACITY_L = 90

PRODUCT_ID = 0xB355          # arbitrary; the GUI shows /ProductName, not this
VERSION    = '2.0'

# ----------------------------------------------------------------------------
# Transmit  -  command frames. Command checksum (4th byte) = (b0+b1+b2+b3)&0xFF.
# Light/pump commands TOGGLE that output like a key press; "all off" is absolute.
# The unit only registers a press when it sees the command on >=2 CONSECUTIVE
# polls, so a press is HELD for several frames, not sent once.
# ----------------------------------------------------------------------------
CMD_IDLE      = bytes.fromhex('FF000000FF')   # dominant idle / wake (~15 of 16)
CMD_IDLE_ALT  = bytes.fromhex('FF4000003F')   # alternate idle (every ~16th poll)
CMD_INDOOR    = bytes.fromhex('FF0100C0C0')   # toggle interior light
CMD_OUTDOOR   = bytes.fromhex('FF0200C0C1')   # toggle exterior light
CMD_PUMP      = bytes.fromhex('FF0400C0C3')   # toggle water pump
CMD_AUX       = bytes.fromhex('FF0800C0C7')   # toggle aux (untested)
CMD_ALL_OFF   = bytes.fromhex('FF8000007F')   # everything off
CMD_INIT      = CMD_IDLE

OUTPUT_CMD = {'interior': CMD_INDOOR, 'exterior': CMD_OUTDOOR, 'pump': CMD_PUMP}

# A press = hold the command for PRESS_FRAMES polls (>=2 required), sent at
# PRESS_INTERVAL_MS. Tanks only appear in the full frame when the master
# ALTERNATES the two idle polls; if the physical panel is gone and the Pi is the
# sole master, enable SEND_KEEPALIVE so it replicates that alternation.
SEND_INIT        = True
SEND_KEEPALIVE   = False      # True only if the Pi is the sole bus master
KEEPALIVE_MS     = 100        # ~100 ms works; 60 ms was erratic on Ehuntabi's bus
PRESS_FRAMES     = 8
PRESS_INTERVAL_MS = 100

# ----------------------------------------------------------------------------
# Frame layout  -  cross-checked against Ehuntabi's field-tested NE185/NE187
# decode (github class142/ne-rs485 issue #3), which matches this frame format.
#   Data frames start FF 00. Byte 6 is a device-specific constant (0x02 on the
#   NE185, 0x10 here) that can serve as a structural validity gate; we rely on
#   the checksum instead. Bytes 9 and 14 vary and remain unidentified.
# ----------------------------------------------------------------------------
SYNC0, SYNC1    = 0xFF, 0x00
FRAME_LEN       = 20
FRESH_TANK_BYTE = 5          # low nibble, 3-rod thermometer (this frame: 0x03)
WASTE_TANK_BYTE = 7          # grey tank is BINARY: bit0 = full/empty
SWITCH_BYTE     = 15         # bit0 int, bit1 ext, bit2 pump, bit7 = heartbeat
CAR_BATT_BYTE   = 12         # starter / vehicle battery (0x9B = 12.5 V)
AUX_BATT_BYTE   = 13         # service / auxiliary battery (0xA2 = 13.2 V, matches shunt)

# Optional structural gate: require a known constant at byte 6 (belt-and-braces
# on top of the checksum). Set to None to disable; 0x10 matches this unit.
GATE_BYTE  = None            # e.g. 6
GATE_VALUE = 0x10

# Checksum (field-tested): sum of the payload bytes 5..18, low 8 bits, in the
# last byte. Payload-only, so it's independent of which poll/command is echoed
# in the header. (The spec.md "sum mod 128 + 2" happens to match idle frames
# too but breaks on command echoes.)
VALIDATE_CHECKSUM = True

# Three measuring rods, read as a thermometer (contiguous from the bottom).
# The rods are bits 0, 1, 2, so a full tank is all three: 2^0+2^1+2^2 = 0x07.
#   0x00 = empty (0%), 0x01 = 1/3, 0x03 = 2/3, 0x07 = full.
# Any other value is a non-contiguous / floating-rod reading (the "---" case)
# and is treated as invalid rather than a fake level.
TANK_MAP = {0x00: 0, 0x01: 33, 0x03: 67, 0x07: 100}


def decode_tank(byte):
    """Return (level_percent, status). status 0 = ok, 1 = disconnected/invalid."""
    nibble = byte & 0x0F
    if nibble in TANK_MAP:
        return TANK_MAP[nibble], 0
    return None, 1                        # floating rod / "---"


def decode_voltage(raw):
    """Spec formula U = (value - 30) / 10. Returns None if implausible."""
    v = (raw - 30) / 10.0
    return v if 5.0 <= v <= 20.0 else None


def valid_checksum(frame):
    return (sum(frame[5:FRAME_LEN - 1]) & 0xFF) == frame[FRAME_LEN - 1]


# ----------------------------------------------------------------------------
# Service construction
# ----------------------------------------------------------------------------
def private_bus():
    # Each VeDbusService must own the root path '/' on its connection, so every
    # service needs its OWN connection. Sharing one bus makes the second service
    # fail with "there is already a handler" for '/'.
    if 'DBUS_SESSION_BUS_ADDRESS' in os.environ:
        return dbus.SessionBus(private=True)
    return dbus.SystemBus(private=True)


def new_service(name, instance, product_name, paths, writable=None):
    svc = VeDbusService(name, bus=private_bus(), register=False)
    svc.add_path('/Mgmt/ProcessName', __file__)
    svc.add_path('/Mgmt/ProcessVersion', VERSION)
    svc.add_path('/Mgmt/Connection', 'RS-485 ' + SERIAL_PORT)
    svc.add_path('/DeviceInstance', instance)
    svc.add_path('/ProductId', PRODUCT_ID)
    svc.add_path('/ProductName', product_name)
    svc.add_path('/FirmwareVersion', VERSION)
    svc.add_path('/HardwareVersion', 0)
    svc.add_path('/Connected', 1)
    for path, value in paths.items():
        svc.add_path(path, value)
    for path, (value, cb) in (writable or {}).items():
        svc.add_path(path, value, writeable=True, onchangecallback=cb)
    svc.register()
    return svc


def build_services():
    fresh = new_service(
        'com.victronenergy.tank.ne355_fresh', 0, 'NE355 Fresh Water',
        {'/Level': 0, '/Capacity': FRESH_CAPACITY_L / 1000.0,
         '/Remaining': 0, '/FluidType': 1, '/Status': 0})

    waste = new_service(
        'com.victronenergy.tank.ne355_waste', 1, 'NE355 Waste Water',
        {'/Level': 0, '/Capacity': WASTE_CAPACITY_L / 1000.0,
         '/Remaining': 0, '/FluidType': 2, '/Status': 0})

    car = new_service(
        'com.victronenergy.battery.ne355_car', 20, 'NE355 Starter Battery',
        {'/Dc/0/Voltage': None})

    aux = new_service(
        'com.victronenergy.battery.ne355_aux', 21, 'NE355 Auxiliary Battery',
        {'/Dc/0/Voltage': None})

    # Switch outputs are now controllable: a State write triggers the matching
    # toggle command on the bus. ShowUIControl on so the GUI renders a switch.
    switch_paths = {'/Debug/LastMessage': ''}
    switch_writable = {}
    for out_id, label in (('interior', 'Interior Light'),
                          ('exterior', 'Exterior Light'),
                          ('pump',     'Water Pump')):
        base = '/SwitchableOutput/%s' % out_id
        switch_paths[base + '/Status'] = 0
        switch_paths[base + '/Name']   = label
        switch_paths[base + '/Settings/Type']          = 1   # toggle
        switch_paths[base + '/Settings/ValidTypes']    = 2
        switch_paths[base + '/Settings/CustomName']    = ''
        switch_paths[base + '/Settings/Group']         = ''
        switch_paths[base + '/Settings/ShowUIControl'] = 1
        switch_writable[base + '/State'] = (0, on_switch_change)
    switch = new_service('com.victronenergy.switch.ne355', 30,
                         'NE355 Panel', switch_paths, switch_writable)

    return {'fresh': fresh, 'waste': waste, 'car': car,
            'aux': aux, 'switch': switch}


# ----------------------------------------------------------------------------
# Serial reading
# ----------------------------------------------------------------------------
read_buffer = bytearray()

# Serial handle + last-known actual output states, shared with the write
# callback. Filled in by main() once the port is open.
tx = {'ser': None, 'state': {'interior': 0, 'exterior': 0, 'pump': 0},
      'press_cmd': None, 'press_left': 0, 'press_active': False,
      'poll_count': 0}


def send_command(cmd):
    """Transmit a 5-byte command frame and resync the receiver."""
    ser = tx['ser']
    if ser is None:
        return
    try:
        ser.write(cmd)
        ser.flush()
        # If the RS-485 adapter loops its own TX back to RX, this drops the
        # echo so it can't be mis-parsed as a data frame.
        ser.reset_input_buffer()
        read_buffer.clear()
    except Exception:
        pass


def on_switch_change(path, value):
    """GUI wrote a new desired state -> hold the toggle key if it differs.

    The command is a toggle, so we compare against the last actual state read
    from the bus and only press when they differ. The press is HELD for several
    frames because the unit ignores a single button frame. The next RX frame
    confirms (or reverts) the displayed state, so a press that doesn't take
    effect self-corrects.
    """
    out = path.split('/')[2]            # /SwitchableOutput/<out>/State
    cmd = OUTPUT_CMD.get(out)
    if cmd is None:
        return False
    desired = 1 if value else 0
    if desired != tx['state'].get(out, 0):
        start_press(cmd)
    return True                         # accept the write; RX is the source of truth


def start_press(cmd):
    tx['press_cmd'] = cmd
    tx['press_left'] = PRESS_FRAMES
    if not tx['press_active']:
        tx['press_active'] = True
        GLib.timeout_add(PRESS_INTERVAL_MS, press_tick)


def press_tick():
    if tx['press_left'] > 0:
        send_command(tx['press_cmd'])
        tx['press_left'] -= 1
        return True                     # keep holding
    tx['press_active'] = False
    return False                        # done -> stop the timer


def send_keepalive():
    # A press in progress owns the bus; don't interleave idle frames with it.
    if not tx['press_active']:
        tx['poll_count'] += 1
        send_command(CMD_IDLE_ALT if tx['poll_count'] % 16 == 0 else CMD_IDLE)
    return True


def read_ne355_data(ser, svc):
    global read_buffer
    try:
        waiting = ser.in_waiting
        if waiting:
            read_buffer.extend(ser.read(waiting))

        while len(read_buffer) >= FRAME_LEN:
            if read_buffer[0] == SYNC0 and read_buffer[1] == SYNC1:
                frame = bytes(read_buffer[:FRAME_LEN])
                gate_ok = GATE_BYTE is None or frame[GATE_BYTE] == GATE_VALUE
                if gate_ok and (not VALIDATE_CHECKSUM or valid_checksum(frame)):
                    del read_buffer[:FRAME_LEN]
                    update_from_frame(svc, frame)
                else:
                    del read_buffer[:1]  # bad frame -> false sync, resync
            else:
                del read_buffer[:1]      # resync one byte at a time

        if len(read_buffer) > 200:
            read_buffer.clear()
    except Exception:
        pass
    return True


def update_tank(tank_svc, byte):
    level, status = decode_tank(byte)
    tank_svc['/Status'] = status
    if level is not None:                  # keep last good level on invalid reads
        tank_svc['/Level']     = level
        tank_svc['/Remaining'] = level / 100.0 * tank_svc['/Capacity']


def update_from_frame(svc, frame):
    # Fresh tank: 3-rod thermometer. Grey/waste tank: single float switch (bit0).
    update_tank(svc['fresh'], frame[FRESH_TANK_BYTE])
    waste_level = 100 if (frame[WASTE_TANK_BYTE] & 0x01) else 0
    svc['waste']['/Status']    = 0
    svc['waste']['/Level']     = waste_level
    svc['waste']['/Remaining'] = waste_level / 100.0 * svc['waste']['/Capacity']

    # Batteries (car = starter byte 12, aux = service byte 13; byte 13
    # confirmed against the SmartShunt at 13.2 V). Publish only plausible reads.
    vc = decode_voltage(frame[CAR_BATT_BYTE])
    if vc is not None:
        svc['car']['/Dc/0/Voltage'] = vc
    vh = decode_voltage(frame[AUX_BATT_BYTE])
    if vh is not None:
        svc['aux']['/Dc/0/Voltage'] = vh

    # Switches - RX is the source of truth. Record actual states for the toggle
    # comparison, and mirror them to D-Bus (local_set_value, so this does NOT
    # re-fire on_switch_change and cannot create a feedback loop).
    s = frame[SWITCH_BYTE]
    states = {'interior': s & 0x01,
              'exterior': (s >> 1) & 0x01,
              'pump':     (s >> 2) & 0x01}
    tx['state'] = states
    for out_id, val in states.items():
        svc['switch']['/SwitchableOutput/%s/State' % out_id] = val
    svc['switch']['/Debug/LastMessage'] = ' '.join('%02X' % b for b in frame)


def main():
    DBusGMainLoop(set_as_default=True)
    svc = build_services()

    ser = serial.Serial(SERIAL_PORT, BAUD, timeout=0)
    tx['ser'] = ser                     # enable the write callback

    if SEND_INIT:
        send_command(CMD_INIT)          # wake the bus so the first press lands
    if SEND_KEEPALIVE:
        GLib.timeout_add(KEEPALIVE_MS, send_keepalive)

    GLib.timeout_add(100, read_ne355_data, ser, svc)
    GLib.MainLoop().run()


if __name__ == '__main__':
    main()