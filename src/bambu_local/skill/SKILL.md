---
name: bambu.local
description: Use when reading a Bambu Lab printer's state, sending it a command, or putting a sliced file on its storage over the local network, with no cloud account. Python package `bambu-local`, imported as `bambu_local`. Also use when a connection to the printer fails with "No route to host" or is refused.
---

# Talking to a Bambu Lab printer on the LAN

```python
import bambu_local as bambu
serial, code = bambu.credentials()     # from Bambu Studio's file, or pass your own
state = bambu.report(host, serial, code)
state["print"]["gcode_state"], state["print"].get("print_error"), state["print"].get("layer_num")
```

## Rules

- Never print or log the access code.
- `upload` starts nothing. Starting a print is the person's decision, so ask first.
- `command` does not confirm anything. Read `report` afterwards and compare.
- `delete` cannot be undone. Look at the name in `files` first.
- A printer that is off fails to connect, and that is the answer. Do not read it as a failed print.

## Reading a stop

`gcode_state` FAILED with `print_error` names the cause. The number in hexadecimal is the code in Bambu's error list (`0x05FF803C` is written 05FF-803C). `layer_num` 0 means nothing was laid down.

## When it does not connect

- `[Errno 65] No route to host` while `ping` answers means macOS refused this program the local network. The setting is the person's, under Privacy & Security, Local Network.
- `PermissionError` means the access code is wrong. The code changes when it is reset on the printer.
- A timeout means the printer is off, asleep or on another network.
