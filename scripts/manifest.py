"""Validate generated artifact links/provenance and record exact source/evidence hashes."""
import gzip
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tarfile
import sys
sys.path.insert(0,str(Path(__file__).parent))
from guard import CACHE,allocated,check

def sha(data):return hashlib.sha256(data).hexdigest()

class Links(HTMLParser):
    def __init__(self):super().__init__();self.href=[];self.images=[]
    def handle_starttag(self,tag,attrs):
        d=dict(attrs)
        if tag=="a" and "href" in d:self.href.append(d["href"])
        if tag=="img":self.images.append(d.get("src",""))

check();out=Path("evidence");r=json.loads((out/"results.json").read_text())
assert r["input_sha256"]==sha((out/"frozen-inputs.json").read_bytes())
assert r["binary_sha256"]==sha((CACHE/"build/actuator_lab").read_bytes())
for name,want in r["source_sha256"].items():assert sha(Path(name).read_bytes())==want,name
assert len(r["monte_carlo"])==64 and all(c["passed"] for c in r["checks"])
for group in r["named"]:
    for kind in ("direct","cascaded","feedforward"):
        data=gzip.decompress((out/"traces"/f"{group['scenario']}-{kind}.csv.gz").read_bytes())
        assert sha(data)==group[kind]["trace_sha256"]
for pair in r["monte_carlo"][:2]:
    for kind in ("direct","cascaded","feedforward"):
        data=gzip.decompress((out/"traces"/f"trial-{pair['id']}-{kind}.csv.gz").read_bytes())
        assert sha(data)==pair[kind]["trace_sha256"]
checkpoint=out/"checkpoints/original-paired"
old=json.loads((checkpoint/"results.json").read_text())
with tarfile.open(checkpoint/"source.tar.gz") as archive:
    for member in archive.getmembers():assert sha(archive.extractfile(member).read())==old["source_sha256"][member.name]
links=Links();links.feed((out/"report.html").read_text())
assert len(links.images)==5 and all(s.startswith("data:image/png;base64,") for s in links.images)
for href in links.href:assert (out/href).is_file(),href
assert len(list((out/"figures").glob("*.pdf")))==5
for p in (out/"figures").glob("*.pdf"):assert p.read_bytes().startswith(b"%PDF-")
excluded_parts={".git", ".venv", "__pycache__", ".pytest_cache"}
files=[p for p in Path(".").rglob("*") if p.is_file() and not excluded_parts.intersection(p.parts) and p.name!="manifest.json" and p.name!="final-checks.txt"]
evidence_size=sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
assert evidence_size<20*1024**2
result={"checks":"current source/binary/input hashes, all retained trace hashes, original checkpoint source hashes, report images/links/PDFs and evidence budget passed","source_and_evidence":{str(p):{"bytes":p.stat().st_size,"sha256":sha(p.read_bytes())} for p in sorted(files)},"evidence_bytes":evidence_size,"allocated_cache_bytes":allocated(CACHE),"test_log":"final-checks.txt is excluded because the verification command is still writing it; actual checks are printed there."}
(out/"manifest.json").write_text(json.dumps(result,indent=2)+"\n")
print(f"Artifact validation passed: {len(files)} files, {evidence_size} evidence bytes, {allocated(CACHE)} allocated cache bytes")
