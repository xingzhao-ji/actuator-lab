import json
import os
from pathlib import Path
import subprocess
import pytest

BINARY = Path(os.environ.get("ACTUATOR_CACHE", Path.home()/".cache/job-apps-runtime/actuator-lab"))/"build/actuator_lab"

def run(output, *args):
    return subprocess.run([str(BINARY),"simulate","--output",str(output),*map(str,args)],capture_output=True,text=True,timeout=15)

@pytest.mark.parametrize("args",[
    ["--nope","1"],["--ticks","1.5"],["--ticks","-1"],["--ticks","12001"],
    ["--target","nan"],["--target","inf"],["--Jb","0"],["--Jb","1junk"],
    ["--substeps","1"],["--substeps","1001"],["--ticks","6000","--substeps","1000"],
    ["--target","0","--target","1"],["--scenario","alien"],["--controller","fake"],
    ["--fault-voltage","13"],["--pulse","0.051"],["--Tc","0.013"],
    ["--scenario","drag","--b","0.1"],
])
def test_invalid_input_never_publishes(tmp_path,args):
    out=tmp_path/"run"
    assert run(out,*args).returncode != 0
    assert not out.exists()

def test_real_roundtrip_complete_pair(tmp_path):
    out=tmp_path/"run";p=run(out,"--ticks",10,"--target",0)
    assert p.returncode==0,p.stderr
    summary=json.loads((out/"summary.json").read_text())
    assert summary["config"]["ticks"]==10
    assert summary["config"]["controller"]=="cascaded"
    assert summary["completed_steps"]==200 and not summary["success"]
    lines=(out/"trace.csv").read_text().splitlines()
    assert len(lines)==12
    assert float(lines[-1].split(",")[0])==.1
    assert not list(tmp_path.glob("*.tmp-*"))

def test_feedforward_is_distinct_reported_controller(tmp_path):
    out=tmp_path/"run";p=run(out,"--controller","feedforward","--ticks",10)
    assert p.returncode==0,p.stderr
    assert json.loads((out/"summary.json").read_text())["config"]["controller"]=="feedforward"

def test_output_conflict_and_missing_parent_preserve_existing(tmp_path):
    out=tmp_path/"run";out.mkdir();(out/"keep").write_text("sentinel")
    assert run(out).returncode!=0 and (out/"keep").read_text()=="sentinel"
    assert run(tmp_path/"missing"/"run").returncode!=0

def test_dangling_symlink_output_is_not_overwritten(tmp_path):
    out=tmp_path/"run";out.symlink_to(tmp_path/"does-not-exist")
    assert run(out,"--ticks",1).returncode!=0
    assert out.is_symlink()

def test_aborted_run_is_explicit_failed_result(tmp_path):
    out=tmp_path/"run"
    p=run(out,"--scenario","fixed","--ticks",12000,"--fixed-voltage",12,"--external",.05)
    assert p.returncode==3,p.stderr
    s=json.loads((out/"summary.json").read_text())
    assert s["aborted"] and not s["success"] and s["completed_steps"]<240000
    assert s["events"][-1].startswith("abort@")
