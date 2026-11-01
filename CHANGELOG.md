# Changelog

## 0.1.0

- `report`, `command` and `credentials` read a printer's state and send it commands over MQTT on port 8883.
- `upload`, `files` and `delete` use its storage over implicit FTPS on port 990, reusing the TLS session on each data connection as the printer requires.
