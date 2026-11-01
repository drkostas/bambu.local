# Contributing

```bash
pip install -e '.[test]'
pytest -q
```

No printer is needed. To include the round trip on the printer's storage, set `BAMBU_HOST` and `BAMBU_CODE`. It uploads a small text file and deletes it.
