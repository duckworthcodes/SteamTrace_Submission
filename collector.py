#!/usr/bin/env python3
"""SteamTrace v1.0 — authorized Steam-artifact inventory and timeline prototype."""
from __future__ import annotations
import argparse, csv, hashlib, html, json, os, platform, re, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_NAME = "SteamTrace"
APP_VERSION = "1.0.0"
LOG_TS = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(.*)$")
TOKEN = re.compile(r'"((?:\\.|[^"\\])*)"|([{}])|([^\s{}"]+)', re.S)

def utc_iso(timestamp: float | None) -> str | None:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat() if timestamp is not None else None

def sha256_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()

def parse_keyvalues(text: str) -> dict[str, Any]:
    """Parse the common quoted-key/value and nested-brace subset of Valve KeyValues."""
    # Strip // comments outside quoted strings.
    cleaned=[]; quoted=False; escaped=False; i=0
    while i < len(text):
        if quoted:
            cleaned.append(text[i])
            if escaped: escaped=False
            elif text[i]=="\\": escaped=True
            elif text[i]=='"': quoted=False
            i+=1; continue
        if text[i]=='"': quoted=True; cleaned.append(text[i]); i+=1; continue
        if text.startswith("//",i):
            end=text.find("\n",i)
            if end<0: break
            cleaned.append("\n"); i=end+1; continue
        cleaned.append(text[i]); i+=1
    tokens=[]
    for m in TOKEN.finditer("".join(cleaned)):
        if m.group(1) is not None: tokens.append(("value",bytes(m.group(1),"utf-8").decode("unicode_escape")))
        elif m.group(2): tokens.append((m.group(2),m.group(2)))
        elif m.group(3): tokens.append(("value",m.group(3)))
    idx=0
    def parse_block(expect_close: bool=False):
        nonlocal idx
        obj={}
        while idx<len(tokens):
            typ,val=tokens[idx]
            if typ=="}":
                if not expect_close: raise ValueError("Unexpected closing brace in KeyValues data")
                idx+=1; return obj
            if typ!="{": 
                key=val; idx+=1
                if idx>=len(tokens): raise ValueError(f"Missing value for KeyValues key: {key}")
                next_type,next_val=tokens[idx]
                if next_type=="{":
                    idx+=1; value=parse_block(True)
                elif next_type=="}": raise ValueError(f"Missing value for KeyValues key: {key}")
                else: idx+=1; value=next_val
                if key in obj:
                    old=obj[key]
                    if not isinstance(old,list): obj[key]=[old]
                    obj[key].append(value)
                else: obj[key]=value
            else: raise ValueError("Unexpected opening brace in KeyValues data")
        if expect_close: raise ValueError("Unclosed brace in KeyValues data")
        return obj
    result=parse_block(False)
    if idx!=len(tokens): raise ValueError("Unparsed KeyValues tokens")
    return result

def parse_vdf(path: Path, rel: str) -> tuple[dict[str,Any], list[dict[str,Any]]]:
    raw=path.read_text(encoding="utf-8-sig",errors="replace")
    parsed=parse_keyvalues(raw)
    events=[{
      "event_time_utc":None,"event_type":"STEAM_CONFIG_PARSED","source_path":rel,
      "description":"Valve KeyValues configuration parsed; values retained as structured artifact data.",
      "details":{"top_level_keys":list(parsed.keys()),"parsed_data":parsed},
      "confidence":"high_for_file_content","timestamp_basis":"no event timestamp inferred"
    }]
    return parsed,events

def parse_steam_log(path: Path, rel: str) -> list[dict[str,Any]]:
    events=[]
    for line_no,line in enumerate(path.read_text(encoding="utf-8-sig",errors="replace").splitlines(),1):
        m=LOG_TS.match(line.strip())
        if not m: continue
        try: ts=datetime.strptime(m.group(1),"%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
        except ValueError: continue
        message=m.group(2).strip()
        event_type="STEAM_LOG_EVENT"
        if "update started" in message.lower(): event_type="STEAM_APP_UPDATE_STARTED"
        elif "update completed" in message.lower(): event_type="STEAM_APP_UPDATE_COMPLETED"
        elif "download queued" in message.lower(): event_type="STEAM_DOWNLOAD_QUEUED"
        events.append({
          "event_time_utc":ts,"event_type":event_type,"source_path":rel,
          "description":message,"details":{"line_number":line_no},
          "confidence":"medium_timestamp_from_log_text","timestamp_basis":"timestamp string parsed from log line"
        })
    return events

def collect_file(path: Path, root: Path) -> dict[str,Any]:
    st=path.stat(follow_symlinks=False)
    birth=getattr(st,"st_birthtime",None); label="birth_time"
    if birth is None and os.name=="nt": birth=st.st_ctime; label="creation_time_windows"
    elif birth is None: label="not_available"
    return {"relative_path":path.relative_to(root).as_posix(),"file_name":path.name,
      "extension":path.suffix.lower(),"size_bytes":st.st_size,"sha256":sha256_file(path),
      "modified_utc":utc_iso(st.st_mtime),"created_utc":utc_iso(birth),
      "created_time_source":label,"changed_utc":utc_iso(st.st_ctime) if os.name!="nt" else None,
      "event_type":"FILE_METADATA","collection_status":"HASHED"}

def build_html(report: dict[str,Any], output: Path):
    rows=[]
    for e in report["events"]:
        rows.append("<tr>"+ "".join(f"<td>{html.escape(str(e.get(k) or '—'))}</td>" for k in ["event_time_utc","event_type","source_path","description","confidence"])+"</tr>")
    summary=f"""<div class="cards"><div><b>{report['record_count']}</b><span>Files hashed</span></div><div><b>{report['event_count']}</b><span>Timeline events</span></div><div><b>{report['error_count']}</b><span>Collection errors</span></div></div>"""
    page=f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>SteamTrace Case Report</title><style>
    body{{font:15px/1.5 system-ui,Arial;margin:0;background:#f2f5f9;color:#172033}}header{{background:#101d35;color:white;padding:30px 5vw}}main{{max-width:1150px;margin:24px auto;padding:0 18px}}.cards{{display:flex;gap:14px;flex-wrap:wrap}}.cards div{{background:white;border-radius:12px;padding:18px 24px;min-width:130px;box-shadow:0 2px 8px #15233b12}}.cards b{{display:block;font-size:28px;color:#1767ad}}.cards span{{color:#65738a}}section{{background:white;border-radius:12px;padding:22px;margin:18px 0;overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:10px;border-bottom:1px solid #e4e9f0;text-align:left;vertical-align:top}}th{{background:#f4f7fb}}.muted{{color:#64748b}}.warning{{border-left:4px solid #d58b16;padding:12px;background:#fff8e8}}</style></head><body>
    <header><h1>SteamTrace — Forensic Case Report</h1><div>Version {APP_VERSION} · Case {html.escape(report['case_id'])}</div><div class="muted">Generated {html.escape(report['collected_at_utc'])}</div></header><main>{summary}
    <section><h2>Collection details</h2><p><b>Examiner:</b> {html.escape(report['examiner'])}</p><p><b>Source directory:</b> {html.escape(report['source_directory'])}</p><p><b>Host:</b> {html.escape(report['host_platform'])}</p><p><b>Hash:</b> SHA-256</p></section>
    <section><h2>Unified event timeline</h2><table><thead><tr><th>Event time (UTC)</th><th>Event type</th><th>Source</th><th>Description</th><th>Confidence / basis</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
    <section><h2>File inventory</h2><table><thead><tr><th>Path</th><th>Size</th><th>SHA-256</th><th>Modified (UTC)</th></tr></thead><tbody>{''.join('<tr>'+''.join(f'<td>{html.escape(str(x.get(k) or "—"))}</td>' for k in ['relative_path','size_bytes','sha256','modified_utc'])+'</tr>' for x in report['records'])}</tbody></table></section>
    <section class="warning"><b>Interpretation limits:</b> File metadata and log timestamps do not independently prove a human action or identify a user. Configuration values describe file contents, not execution. Synthetic fixtures are training data. This prototype is not a validated forensic suite; preserve originals and document acquisition separately.</section>
    </main></body></html>"""
    (output/"case_report.html").write_text(page,encoding="utf-8")

def run_collection(source: Path, output: Path, case_id: str, examiner: str):
    if not source.exists() or not source.is_dir(): raise ValueError(f"Evidence directory not found: {source}")
    if output==source or source in output.parents: raise ValueError("Output folder must be outside the evidence directory.")
    records=[]; errors=[]; events=[]
    for current,dirs,files in os.walk(source,followlinks=False):
        cp=Path(current); dirs[:]=[d for d in dirs if not (cp/d).is_symlink()]
        for fn in sorted(files):
            f=cp/fn
            if f.is_symlink(): continue
            rel=f.relative_to(source).as_posix()
            try:
                rec=collect_file(f,source); records.append(rec)
                if f.suffix.lower()==".vdf":
                    try: _,parsed=parse_vdf(f,rel); events.extend(parsed)
                    except (ValueError,UnicodeError) as exc: errors.append({"path":rel,"stage":"vdf_parse","error":str(exc)})
                elif f.suffix.lower()==".txt" and ("log" in f.name.lower() or "content" in f.name.lower()):
                    try: events.extend(parse_steam_log(f,rel))
                    except OSError as exc: errors.append({"path":rel,"stage":"log_parse","error":str(exc)})
            except OSError as exc: errors.append({"path":rel,"stage":"collection","error":str(exc)})
    for r in records:
        events.append({"event_time_utc":r["modified_utc"],"event_type":"FILE_METADATA","source_path":r["relative_path"],
          "description":f"File inventoried and SHA-256 hashed ({r['size_bytes']} bytes).",
          "details":{"sha256":r["sha256"],"extension":r["extension"]},
          "confidence":"high_for_observed_metadata","timestamp_basis":"filesystem modification time"})
    events.sort(key=lambda e:(e["event_time_utc"] or "",e["source_path"],e["event_type"]))
    output.mkdir(parents=True,exist_ok=True)
    collected=datetime.now(timezone.utc).isoformat()
    report={"tool":APP_NAME,"version":APP_VERSION,"case_id":case_id,"examiner":examiner,
      "collected_at_utc":collected,"source_directory":str(source),"host_platform":platform.platform(),
      "record_count":len(records),"event_count":len(events),"error_count":len(errors),
      "timestamp_note":"Filesystem and log timestamps are source data, not proof of user activity.",
      "records":records,"events":events,"errors":errors}
    (output/"timeline.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    fields=["relative_path","file_name","extension","size_bytes","sha256","modified_utc","created_utc","created_time_source","changed_utc","event_type","collection_status"]
    with (output/"timeline.csv").open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(records)
    with (output/"events.csv").open("w",newline="",encoding="utf-8-sig") as f:
        cols=["event_time_utc","event_type","source_path","description","confidence","timestamp_basis"]
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
        for e in events: w.writerow({k:e.get(k) for k in cols})
    manifest={"tool":APP_NAME,"version":APP_VERSION,"case_id":case_id,"generated_at_utc":collected,
      "hash_algorithm":"SHA-256","hashed_file_count":len(records),
      "files":[{"path":r["relative_path"],"sha256":r["sha256"]} for r in records]}
    (output/"evidence_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    (output/"collection_errors.json").write_text(json.dumps(errors,indent=2),encoding="utf-8")
    build_html(report,output)
    return report

def main():
    ap=argparse.ArgumentParser(description="Inventory authorized Steam-related evidence and parse selected artifact formats.")
    ap.add_argument("evidence_dir"); ap.add_argument("-o","--output",default="steamtrace_output")
    ap.add_argument("--case-id",default="UNASSIGNED"); ap.add_argument("--examiner",default="Not specified")
    a=ap.parse_args()
    try:
        r=run_collection(Path(a.evidence_dir).expanduser().resolve(),Path(a.output).expanduser().resolve(),a.case_id,a.examiner)
    except (ValueError,OSError) as exc: ap.error(str(exc))
    print(f"{APP_NAME} {APP_VERSION}")
    print(f"Files hashed: {r['record_count']}")
    print(f"Timeline events: {r['event_count']}")
    print(f"Collection / parsing errors: {r['error_count']}")
    print(f"Case report: {Path(a.output).resolve()/'case_report.html'}")
    return 0 if not r["errors"] else 2
if __name__=="__main__": raise SystemExit(main())
