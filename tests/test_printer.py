"""The hand-written MQTT, checked against the specification. No printer is needed."""
import json
import struct

import bambu_local
from bambu_local import printer as P


class FakeSock:
    def __init__(self, script: bytes):
        self.data = script

    def recv(self, n):
        chunk, self.data = self.data[:n], self.data[n:]
        return chunk                           # b"" for ever once spent, as a closed TLS socket does


def publish(obj: dict) -> bytes:
    body = struct.pack("!H", 5) + b"topic" + json.dumps(obj).encode()
    return bytes([0x30]) + P._remaining_length(len(body)) + body


def test_remaining_length_at_its_boundaries():
    assert P._remaining_length(0) == b"\x00"
    assert P._remaining_length(127) == b"\x7f"
    assert P._remaining_length(128) == b"\x80\x01"
    assert P._remaining_length(16383) == b"\xff\x7f"
    assert P._remaining_length(16384) == b"\x80\x80\x01"
    assert P._remaining_length(9654) == b"\xb6\x4b"


def test_remaining_length_reads_back_what_it_writes():
    for n in (0, 127, 128, 9654, 16384, 2097152):
        assert P._read_remaining_length(FakeSock(P._remaining_length(n))) == n


def test_string_carries_its_length():
    assert P._string("MQTT") == b"\x00\x04MQTT"
    assert P._string("") == b"\x00\x00"


def test_connect_packet_shape():
    packet = P._connect_packet("12345678")
    assert packet[0] == 0x10
    body = packet[2:]
    assert packet[1] == len(body)
    assert body[:6] == b"\x00\x04MQTT"
    assert body[6] == 4                        # MQTT 3.1.1
    assert body[7] == 0xC0                     # a username and a password follow
    assert struct.unpack("!H", body[8:10])[0] == 60
    assert body.endswith(P._string("bblp") + P._string("12345678"))


def test_credentials_reads_the_first_pair(tmp_path):
    conf = tmp_path / "BambuStudio.conf"
    conf.write_text(json.dumps({"access_code": {"": "x", "SERIAL1": 12345678}}))
    assert bambu_local.credentials(conf) == ("SERIAL1", "12345678")


def test_credentials_finds_nothing_without_raising(tmp_path):
    assert bambu_local.credentials(tmp_path / "absent.conf") is None
    bad = tmp_path / "bad.conf"
    bad.write_text("not json")
    assert bambu_local.credentials(bad) is None
    empty = tmp_path / "empty.conf"
    empty.write_text("{}")
    assert bambu_local.credentials(empty) is None


def test_a_packet_cut_off_mid_body_returns_and_does_not_spin():
    cut = bytes([0x90]) + P._remaining_length(50) + b"only ten b"
    assert P._read_reports(FakeSock(cut), deadline=float("inf")) == {}


def test_deltas_merge_and_the_read_stops_once_the_state_is_known():
    script = publish({"print": {"bed_temper": 20}}) + publish({"print": {"gcode_state": "IDLE"}}) \
        + publish({"print": {"bed_temper": 99}})
    got = P._read_reports(FakeSock(script), deadline=float("inf"))
    assert got == {"print": {"bed_temper": 20, "gcode_state": "IDLE"}}


def test_a_printer_that_never_says_its_state_is_cut_off_at_the_deadline():
    ticks = iter(range(1000))
    got = P._read_reports(FakeSock(publish({"print": {"bed_temper": 20}}) * 200), deadline=5,
                          clock=lambda: next(ticks))
    assert got == {"print": {"bed_temper": 20}}


def test_a_message_that_is_not_json_is_skipped():
    body = struct.pack("!H", 1) + b"t" + b"not json"
    script = bytes([0x30]) + P._remaining_length(len(body)) + body + publish({"print": {"gcode_state": "RUNNING"}})
    assert P._read_reports(FakeSock(script), deadline=float("inf"))["print"]["gcode_state"] == "RUNNING"
