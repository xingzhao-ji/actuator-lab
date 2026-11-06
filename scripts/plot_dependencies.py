"""Install pinned plotting wheels in a project-only target; never mutate NumPy/SciPy."""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
from guard import CACHE,check,allocated

PINS=["matplotlib==3.10.7","contourpy==1.4.0","cycler==0.12.1","fonttools==4.67.0","kiwisolver==1.5.1","pillow==13.0.0","pyparsing==3.3.3"]
check()
report=CACHE/"plot-plan.json"
base=[sys.executable,"-m","pip","install","--no-cache-dir","--only-binary=:all:","--no-deps"]
subprocess.run(base+["--dry-run","--ignore-installed","--report",str(report),*PINS],check=True)
plan=json.loads(report.read_text());wheels=[]
for item in plan["install"]:
    url=item["download_info"]["url"]
    if not url.endswith(".whl"):raise RuntimeError("non-wheel dependency")
    with urllib.request.urlopen(urllib.request.Request(url,method="HEAD"),timeout=30) as response:size=int(response.headers["Content-Length"])
    wheels.append({"name":item["metadata"]["name"],"version":item["metadata"]["version"],"bytes":size,"url":url,"sha256":item["download_info"]["archive_info"]["hashes"]["sha256"]})
total=sum(w["bytes"] for w in wheels)
if total>25*1024**2:raise RuntimeError("plot wheel download exceeds 25 MiB bound")
(CACHE/"plot-wheel-sizes.json").write_text(json.dumps({"total_bytes":total,"wheels":wheels},indent=2)+"\n")
print(f"Inspected {len(wheels)} wheels, {total} download bytes; existing cache {allocated(CACHE)} bytes",flush=True)
if not (CACHE/"plot-site/matplotlib").exists():
    subprocess.run(base+["--target",str(CACHE/"plot-site"),*PINS],check=True)
check()
env=dict(os.environ,PYTHONPATH=str(CACHE/"plot-site"))
subprocess.run([sys.executable,"-c","import matplotlib,numpy,scipy; print(matplotlib.__version__, numpy.__version__, scipy.__version__)"],env=env,check=True)
