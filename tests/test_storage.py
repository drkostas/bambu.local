"""Reading the printer's file list. `test_live_round_trip` needs a printer and is skipped without one."""
import os

import pytest

import bambu_local
from bambu_local import storage as S


def test_parse_list_takes_files_and_leaves_folders_out():
    lines = ["-rwxr-xr-x 1 root root 1048576 Nov 01 10:00 a card.gcode.3mf",
             "drwxr-xr-x 2 root root 4096 Nov 01 10:00 cache",
             "total 8",
             "-rw-r--r-- 1 root root 0 Jan 02 2026 empty.txt"]
    assert S._parse_list(lines) == [{"name": "a card.gcode.3mf", "size": 1048576},
                                    {"name": "empty.txt", "size": 0}]


@pytest.mark.skipif("BAMBU_HOST" not in os.environ or "BAMBU_CODE" not in os.environ,
                    reason="needs BAMBU_HOST and BAMBU_CODE")
def test_live_round_trip(tmp_path):
    host, code = os.environ["BAMBU_HOST"], os.environ["BAMBU_CODE"]
    local = tmp_path / "bambu-local-test.txt"
    local.write_bytes(b"bambu-local round trip\n")
    assert bambu_local.upload(host, code, local) == {"name": local.name, "size": local.stat().st_size}
    try:
        assert local.name in [f["name"] for f in bambu_local.files(host, code)]
    finally:
        bambu_local.delete(host, code, f"/{local.name}")
    assert local.name not in [f["name"] for f in bambu_local.files(host, code)]
