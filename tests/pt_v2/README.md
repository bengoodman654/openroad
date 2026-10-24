# Offline Public Transport v2 fixture adapters

Run offline deterministic tests:

```bash
python -m unittest discover -s tests/pt_v2 -p 'test_*.py' -v
```

For a **previously obtained** licensed, trustworthy GTFS ZIP, inspect it without networking:

```bash
python tests/pt_v2/inspect_gtfs.py \
  --archive /path/to/official.zip \
  --source-url https://publisher.example/feed \
  --date 2026-10-24 \
  --max-mib 8 \
  --output inspection.json
```

The parser has an 8 MiB core-table default for small fixtures; increasing `--max-mib` up to 256 is an explicit opt-in that must be used **off-host** after resource measurement. Large regional DfT BODS GTFS feeds may exceed these limits and should be processed with a separately measured streaming importer or smaller operator-specific source files. This is **not** an Android or national production GTFS importer.

The optional bounded metadata probe `offhost_gtfs_probe.py` uses **one** official DfT regional GET at most. Its West Midlands attempt stopped at >140 MiB compressed. Do not re-run without reconsidering acquisition strategy and budgets. Its failure is a deliberate safety gate.

Synthetic fixture timetables are invented solely to test parser mechanics and are not intended for passengers. Published service identities are sourced in `docs/public-transport-v2/fixtures/README.md`.

**Never claim a production acceptance case passed from a synthetic fixture, a route-list page or a candidate match in a GTFS ZIP.** End-to-end release gates remain 0/105.
