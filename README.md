# bambu.local

Talk to a Bambu Lab printer over your own network, with no cloud account and no dependencies.

```bash
pip install bambu-local
```

```python
import bambu_local as bambu

serial, code = bambu.credentials()          # the pair Bambu Studio saved, or pass your own
state = bambu.report("192.0.2.10", serial, code)
print(state["print"]["gcode_state"])        # IDLE, RUNNING, PAUSE, FINISH or FAILED

bambu.upload("192.0.2.10", code, "card.gcode.3mf")   # shows on the printer's screen, starts nothing
print(bambu.files("192.0.2.10", code))
```

The access code is on the printer's screen under its network settings.

## What it does

- `report(host, serial, code)` asks the printer for its whole state over MQTT on port 8883.
- `command(host, serial, code, payload)` sends one command. It does not confirm the command worked, so read `report` afterwards and compare.
- `upload`, `files` and `delete` use the printer's storage over implicit FTPS on port 990. `upload` checks that the printer lists the file at the same size.
- `credentials(conf=None)` reads the first serial and access code from Bambu Studio's configuration file.

## What it does not do

It holds no session, so it has no keepalive and no reconnect. It speaks MQTT at QoS 0 only. It is not a general MQTT or FTP library.

The printer's certificate cannot be checked against a public authority, so the connection protects the access code from a passive listener only. Use it on a network you trust.

## On macOS

macOS can refuse a program access to the local network with `[Errno 65] No route to host`, while other programs on the same Mac reach the printer. If `ping` answers and Python does not, look at Privacy & Security, Local Network in System Settings.

## Tested with

A Bambu Lab X2D. Other models use the same ports, but only this one has been tried.
