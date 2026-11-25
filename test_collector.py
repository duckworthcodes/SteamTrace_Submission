import tempfile
import unittest
from pathlib import Path
import sys, json, csv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "steamtrace"))
from collector import sha256_file, collect_file, parse_keyvalues, parse_steam_log, run_collection

class SteamTraceTests(unittest.TestCase):
    def test_sha256_known_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"known.txt"; p.write_text("abc",encoding="utf-8")
            self.assertEqual(sha256_file(p),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_metadata_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); f=root/"fixture.log"; f.write_text("synthetic",encoding="utf-8")
            row=collect_file(f,root)
            self.assertEqual(row["relative_path"],"fixture.log")
            self.assertEqual(row["event_type"],"FILE_METADATA")
            self.assertEqual(len(row["sha256"]),64)

    def test_keyvalues_nested_parse(self):
        parsed=parse_keyvalues('"Root" { "Settings" { "RememberPassword" "0" } }')
        self.assertEqual(parsed["Root"]["Settings"]["RememberPassword"],"0")

    def test_keyvalues_comments_and_duplicate_keys(self):
        parsed=parse_keyvalues('// comment\n"Root" { "Tag" "one" "Tag" "two" }')
        self.assertEqual(parsed["Root"]["Tag"],["one","two"])

    def test_keyvalues_malformed_input(self):
        with self.assertRaises(ValueError): parse_keyvalues('"Root" { "A" "1"')

    def test_steam_log_timestamp_and_event_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"content_log.txt"
            f.write_text("[2026-01-02 03:04:05] App update started: appid=42\n",encoding="utf-8")
            events=parse_steam_log(f,"content_log.txt")
            self.assertEqual(len(events),1)
            self.assertEqual(events[0]["event_type"],"STEAM_APP_UPDATE_STARTED")
            self.assertTrue(events[0]["event_time_utc"].startswith("2026-01-02T03:04:05"))

    def test_end_to_end_outputs_and_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); src=base/"evidence"; out=base/"out"
            (src/"steam/config").mkdir(parents=True); (src/"steam/logs").mkdir(parents=True)
            (src/"steam/config/config.vdf").write_text('"Root" { "Flag" "1" }',encoding="utf-8")
            (src/"steam/logs/content_log.txt").write_text("[2026-01-02 03:04:05] Download queued: appid=42",encoding="utf-8")
            result=run_collection(src,out,"CASE-1","Examiner")
            self.assertEqual(result["record_count"],2)
            self.assertTrue((out/"case_report.html").exists())
            self.assertTrue((out/"events.csv").exists())
            types={e["event_type"] for e in result["events"]}
            self.assertIn("STEAM_CONFIG_PARSED",types)
            self.assertIn("STEAM_DOWNLOAD_QUEUED",types)
            manifest=json.loads((out/"evidence_manifest.json").read_text())
            self.assertEqual(manifest["hashed_file_count"],2)

    def test_empty_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); src=base/"evidence"; src.mkdir()
            result=run_collection(src,base/"out","EMPTY","Tester")
            self.assertEqual(result["record_count"],0)
            self.assertEqual(result["event_count"],0)

if __name__=="__main__": unittest.main()
