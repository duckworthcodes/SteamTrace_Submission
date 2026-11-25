# SteamTrace v1.0
**Cross-Platform Steam Artifact Forensics and Unified Timeline Reconstruction**

SteamTrace is an academic digital-forensics prototype for authorized evidence copies. It inventories files, computes SHA-256 hashes, extracts a limited subset of Valve KeyValues (`.vdf`) configuration content, parses selected timestamped Steam-style log lines, combines parsed and filesystem metadata events into a unified timeline, and generates JSON, CSV, a hash manifest, and an HTML case report.

## Requirements
- Python 3.10+
- Standard library only; no third-party runtime packages required

## Run
```bash
python steamtrace/collector.py sample_evidence -o demo_output --case-id CASE-001 --examiner "Student Name"
python -m unittest discover -s tests -v
```
On Windows, `py -3` may be used instead of `python`.

## Outputs
- `timeline.json` — collection metadata, file records, parsed events, and errors
- `timeline.csv` — file inventory
- `events.csv` — unified event timeline
- `evidence_manifest.json` — SHA-256 path/digest inventory
- `case_report.html` — self-contained investigator-readable report
- `collection_errors.json` — collection and parsing errors (empty when none)

## Supported parsers and boundaries
- `.vdf`: common quoted-key/value and nested-brace subset of Valve KeyValues; preserves parsed data in a `STEAM_CONFIG_PARSED` event. This is not a complete implementation of every KeyValues dialect.
- `content_log*.txt` / `*log*.txt`: lines beginning `[YYYY-MM-DD HH:MM:SS]`; selected phrases are categorized as update-started, update-completed, or download-queued events. Timestamps are treated as UTC for normalized output because the source timezone is not otherwise established; this is an explicit assumption, not proof of original timezone.
- Other files: inventoried and hashed as `FILE_METADATA` events.

## Forensic cautions
- Synthetic sample fixtures are fabricated training data, not real Steam evidence or proof of LuaTools execution.
- Configuration values describe file contents, not execution or user behavior.
- Filesystem and log timestamps do not independently prove a human action or identify a user.
- Reading files to hash them may affect access-time metadata depending on the filesystem and mount options.
- Work from authorized forensic copies or read-only images where possible; document acquisition and chain of custody separately.
- This is not a validated forensic suite. Validate parser behavior against known-good artifacts and controlled ground truth before operational use.
- LuaTools-specific detection, native Steam database parsing, Windows Event Log and Linux journal ingestion remain future work.

## Ethical use
Use only systems and evidence you own or are explicitly authorized to examine. Do not use this tool to access another person's account, bypass DRM, obtain credentials, or evade platform protections.
# SteamTrace_Submission
