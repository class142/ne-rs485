# RS485 protocol of NordElettronica NE185 / NE187

Field notes for the **NordElettronica NE185 main unit** (11S variant) driven via
its **NE187 control panel**, using an ESP32 as RS-485 master. Everything here is
**field-tested on the real motorhome** (lights, pump and all sensors verified).

The command set from [`spec.md`](spec.md) (NE334) carries over **unchanged**, so
this file only documents what differs: the NE185 replies with a **20-byte status
frame** (different layout and checksum from the NE334 response) and needs a
**dual idle poll** to emit tank data.

## Serial config
RS-485, **38400 8N1** (same as the NE334).

## Commands (master → main unit)
Identical to the NE334 command set:

| Command | Meaning |
| --- | --- |
| `FF 01 00 C0 C0` | interior light |
| `FF 02 00 C0 C1` | exterior light |
| `FF 04 00 C0 C3` | water pump |
| `FF 08 00 C0 C7` | aux (from the NE334 repo; not wired on my van, untested) |
| `FF 80 00 00 7F` | all off |

Command checksum = `(b0 + b1 + b2 + b3) & 0xFF` — a plain 8-bit sum works for all
of the above (e.g. `FF+01+00+C0 = 0x1C0 → 0xC0`).

**Toggle / hold:** the unit only registers a press when it sees the button
command on **≥ 2 consecutive polls**; a single frame is ignored. Hold it for
several frames, then return to idle for a couple of frames before allowing the
same button again (avoids a double toggle).

## Idle poll — must ALTERNATE two frames
```
FF 00 00 00 FF   (dominant — sent ~15 of every 16 polls)
FF 40 00 00 3F   (every ~16th poll)
```
Polling with **only** `FF 40 00 00 3F` makes the NE185 drop to a native short
frame (starts `7C E0 …`) that carries **no tank data**. Replicating the panel's
alternation is what makes it emit the full 20-byte frame with tanks. A poll
period of ~**100 ms** works reliably (60 ms was erratic on my bus; my board has
R1 = R2 = 680 Ω bias + 132 Ω termination).

## Status frame (main unit → master) — 20 bytes

| Pos | Value | Meaning |
|-----|-------|---------|
| 0–4 | — | echo of the poll/command |
| 5   | low nibble | fresh-water tank: `0x0` = reserve/empty, `0x1` = 1/4, `0x3` = 2/4, `0x7` = 3/4, `0xF` = full |
| 6   | `0x02` | constant — used as a validity gate (parasitic frames have `0xFF` here) |
| 7   | bit0 | grey-water tank: `0` = empty, `1` = full |
| 8   | `0x40` | constant |
| 9   | variable | unidentified sensor/counter — ignore (but counted in checksum) |
| 10  | `0x00` | constant |
| 11  | `0xFF` | constant (not reliable in master mode — don't gate on it) |
| 12  | raw | service (leisure) battery: `V = (raw − 30) / 10`  *(30 decimal)* |
| 13  | raw | vehicle (starter) battery: `V = (raw − 30) / 10` |
| 14  | variable | unidentified sensor — ignore (but counted in checksum) |
| 15  | bitmap | bit0 = interior light, bit1 = exterior light, bit2 = pump, **bit7 = poll heartbeat (NOT shore)** |
| 16  | bit0 | shore / 230 V mains: `0x31` = mains present, `0x30` = none |
| 17–18 | `0x00` | constant |
| 19  | checksum | **`(sum of bytes 5..18) & 0xFF`** |

**A frame is valid when** `b6 == 0x02` **and** the byte-19 checksum matches.
This checksum differs from the `sum mod 128 + 2` in [`spec.md`](spec.md) — that
one rejected every frame on the NE185.

## How these were confirmed
- **Grey tank (b7):** differential test — bridging the level jumper
  (JP7 pin1 ↔ pin2 = FULL) flipped b7 to `0x01` on 303 frames, back to `0x00`
  with the bridge removed.
- **Shore (b16 bit0):** differential test — plugging/unplugging 230 V mains
  toggled `0x31` / `0x30`.
- **Grey tank is NOT in b6:** an earlier guess put it in b6, but b6 is a constant
  `0x02`; that produced false "grey full" readings.
- Lights, pump, fresh-water level and battery voltages all match the physical
  vehicle.

## Still unidentified (help welcome)
- Bytes **9** and **14**: vary frame-to-frame, meaning unknown (temperature? counters?).
- b15 **bits 3–6**: never seen set on this van (heater? gas? exterior LEDs?).
