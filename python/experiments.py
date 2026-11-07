"""Executed paired experiment and independent numerical verification suite."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import numpy as np
import scipy
from inputs import freeze
from reference import exact_constant,reference_integrate

FIELDS=["theta","omega_body","omega_wheel","current","W_e","Q_R","Q_b","W_ext","I_ext"]
SCALE=np.array([1,1,100,1])
CONTROLLERS=("direct","cascaded","feedforward")

def aggregate(pairs,kinds=("direct","cascaded")):
    counts={"denominator":len(pairs)}
    for kind in kinds:
        for metric in ("success","aborted"):
            values=[pair[kind][metric] for pair in pairs]
            if not all(type(v) is bool for v in values):raise ValueError("nonboolean outcome")
            counts[f"{kind}_{metric}"]=sum(values)
    return counts

def sha(data):return hashlib.sha256(data).hexdigest()

def checkpoint_unchanged(original,named,trials,input_hash):
    """Preserve typed legacy values and CSV bytes across additive JSON schemas."""
    if original['input_sha256'] != input_hash:return False
    excluded={'observational_metrics','summary_sha256','trace_sha256'}
    def legacy(summary):
        return json.dumps({k:v for k,v in summary.items() if k not in excluded},sort_keys=True,allow_nan=False)
    for group,latest,marker in [('named',named,'scenario'),('monte_carlo',trials,'id')]:
        if len(original[group]) != len(latest):return False
        for before,after in zip(original[group],latest):
            if type(before[marker]) is not type(after[marker]) or before[marker] != after[marker]:return False
            for kind in ('direct','cascaded'):
                if before[kind]['trace_sha256'] != after[kind]['trace_sha256'] or legacy(before[kind]) != legacy(after[kind]):return False
    return True

def invoke(binary,options):
    with tempfile.TemporaryDirectory(prefix="experiment-") as folder:
        out=Path(folder)/"run"
        command=[str(binary),"simulate","--output",str(out)]
        for key,value in options.items():command.extend(["--"+key,str(value)])
        process=subprocess.run(command,capture_output=True,text=True,timeout=30)
        if process.returncode not in (0,3):raise RuntimeError(process.stderr)
        summary=json.loads((out/"summary.json").read_text())
        if (process.returncode==3)!=summary["aborted"]:raise RuntimeError("exit/result mismatch")
        data=(out/"trace.csv").read_bytes()
        trace=np.genfromtxt(io.BytesIO(data),delimiter=",",names=True)
        if any(not np.isfinite(trace[name]).all() for name in trace.dtype.names):raise RuntimeError("nonfinite trace")
        return summary,trace,data,sha((out/"summary.json").read_bytes()),sha(data)

def state_matrix(trace):return np.column_stack([trace[name] for name in FIELDS])

def replay(binary,options,keep=None):
    summary,trace,data,summary_sha,trace_sha=invoke(binary,options)
    second,_,_,second_summary_sha,second_trace_sha=invoke(binary,options)
    if summary_sha!=second_summary_sha or trace_sha!=second_trace_sha or summary!=second:raise RuntimeError("nondeterministic replay")
    summary["summary_sha256"]=summary_sha;summary["trace_sha256"]=trace_sha
    if keep:
        keep.parent.mkdir(parents=True,exist_ok=True);keep.write_bytes(gzip.compress(data,mtime=0))
    return summary,trace

def run_suite(binary,outdir):
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    input_hash=freeze(outdir/"frozen-inputs.json")
    frozen=json.loads((outdir/"frozen-inputs.json").read_text())
    checks=[]
    def require(name,condition,detail):
        checks.append({"name":name,"passed":bool(condition),"detail":detail})
        if not condition:raise AssertionError(f"{name}: {detail}")
    convergence=[]
    smooth_config=None
    for n in frozen["smooth_convergence"]["substeps"]:
        s,t=replay(binary,{"scenario":"fixed","Tc":.001,"ticks":25,"substeps":n,"fixed-voltage":1,"external":.003})
        smooth_config=s["config"];ref=reference_integrate(smooth_config)
        exact=exact_constant(smooth_config["initial"],smooth_config["plant"],1,.003,.025)
        x=state_matrix(t)
        convergence.append({"h":.001/n,"state_error":float(np.max(np.abs((x[-1,:4]-exact)/SCALE))),
                            "work_ledger_error_J":float(np.max(np.abs(x[-1,4:8]-ref["states"][-1,4:8]))),
                            "impulse_ledger_error_Nms":float(abs(x[-1,8]-ref["states"][-1,8])),
                            "max_energy_defect":s["max_energy_defect"],"max_momentum_defect":s["max_momentum_defect"]})
        require(f"matrix_vs_DOP853_h{n}",np.max(np.abs((ref["states"][-1,:4]-exact)/SCALE))<1e-10,{"error":float(np.max(np.abs(ref["states"][-1,:4]-exact)))})
    errors=[r["state_error"] for r in convergence]
    ratios=[errors[n]/errors[n+1] for n in range(2)]
    require("smooth_default_scaled_state",errors[1]<1e-6,{"error":errors[1]})
    require("smooth_fourth_order",all(12<ratio<22 for ratio in ratios),{"ratios":ratios,"horizon":.025})
    energy_ratios=[convergence[n]["max_energy_defect"]/convergence[n+1]["max_energy_defect"] for n in range(2)]
    require("smooth_fourth_order_work_balance",all(12<ratio<22 for ratio in energy_ratios),{"ratios":energy_ratios})
    normal_ref=reference_integrate(smooth_config);tight_ref=reference_integrate(smooth_config,rtol=2e-13,atol=2e-14)
    sensitivity=float(np.max(np.abs(normal_ref["states"]-tight_ref["states"])))
    require("reference_sensitivity",sensitivity<1e-10,{"max_absolute":sensitivity})
    print("Smooth convergence checked; running seven named cases with original controllers and follow-up feedforward ablation.",flush=True)
    named=[];reference_checks=[]
    for case in frozen["named_cases"]:
        pair={"scenario":case}
        for kind in CONTROLLERS:
            summary,trace=replay(binary,{"scenario":case,"controller":kind},outdir/"traces"/f"{case}-{kind}.csv.gz")
            pair[kind]=summary
            require(f"{case}_{kind}_finite_completion",not summary["aborted"],{"reason":summary["reason"]})
            require(f"{case}_{kind}_momentum",summary["max_momentum_defect"]<1e-10,{"defect":summary["max_momentum_defect"]})
            require(f"{case}_{kind}_losses",np.all(trace["Q_R"]>=-1e-14) and np.all(trace["Q_b"]>=-1e-14) and np.all(np.diff(trace["Q_R"])>=-1e-14) and np.all(np.diff(trace["Q_b"])>=-1e-14),{})
            # Every scenario independently replays applied voltage; nominal/pulse also close the independent loop.
            ref=reference_integrate(summary["config"],trace["voltage"][:-1])
            matrix=state_matrix(trace)
            state_error=float(np.max(np.abs((matrix[:,:4]-ref["states"][:,:4])/SCALE)))
            work_error=float(np.max(np.abs(matrix[:,4:8]-ref["states"][:,4:8])))
            impulse_error=float(np.max(np.abs(matrix[:,8]-ref["states"][:,8])))
            check={"case":case,"controller":kind,"plant_replay_scaled_state_error":state_error,"work_ledger_error_J":work_error,"impulse_ledger_error_Nms":impulse_error}
            require(f"{case}_{kind}_independent_plant",state_error<2e-6,{"error":state_error})
            require(f"{case}_{kind}_independent_work",work_error<2e-5 and impulse_error<1e-10,check)
            if case in ("nominal","pulse"):
                closed=reference_integrate(summary["config"])
                closed_error=float(np.max(np.abs((matrix[:,:4]-closed["states"][:,:4])/SCALE)))
                command_error=float(np.max(np.abs(trace["voltage"][:-1]-closed["voltage"])))
                check.update(closed_loop_scaled_state_error=closed_error,closed_loop_voltage_error=command_error)
                require(f"{case}_{kind}_independent_controller",closed_error<2e-6 and command_error<2e-5,check)
            reference_checks.append(check)
        named.append(pair)
        print(f"Named case {case}: "+", ".join(f"{k} success={pair[k]['success']}" for k in CONTROLLERS),flush=True)
    print("Running all frozen paired Monte Carlo trials, each twice for deterministic replay.",flush=True)
    trials=[]
    for trial in frozen["trials"]:
        pair={"id":trial["id"]}
        for kind in CONTROLLERS:
            keep=outdir/"traces"/f"trial-{trial['id']}-{kind}.csv.gz" if trial["id"]<2 else None
            summary,_=replay(binary,{**trial["options"],"controller":kind},keep)
            pair[kind]=summary
        trials.append(pair)
    counts=aggregate(trials,CONTROLLERS)
    require("all_frozen_trials_retained",counts["denominator"]==64 and [p["id"] for p in trials]==list(range(64)),counts)
    require("stuck_fault_failure_retained",all(not named[5][kind]["success"] and named[5][kind]["excursion"] for kind in CONTROLLERS),{})
    original_path=outdir/"checkpoints/original-paired/results.json"
    if original_path.exists():
        original=json.loads(original_path.read_text())
        require("original_paired_outputs_unchanged",checkpoint_unchanged(original,named,trials,input_hash),
                {"checkpoint":str(original_path),"contract":"typed legacy fields and exact CSV hashes; additive raw summaries retain separate deterministic hashes"})
    source_files=[p for folder in ("src","include","python","scripts","tests") for p in Path(folder).rglob("*") if p.is_file() and "__pycache__" not in str(p)] + [Path("Makefile")]
    source_hashes={str(p):sha(p.read_bytes()) for p in sorted(source_files)}
    result={"schema_version":1,"input_sha256":input_hash,"binary_sha256":sha(Path(binary).read_bytes()),"source_sha256":source_hashes,
            "versions":{"python":platform.python_version(),"numpy":np.__version__,"scipy":scipy.__version__,"platform":platform.platform()},
            "convergence":convergence,"reference_checks":reference_checks,"checks":checks,"named":named,"monte_carlo":trials,"aggregate":counts,
            "follow_up":"Feedforward is a post-observation ablation: cascade with Kc=KI=0, same frozen inputs, no tuning or resampling. Original paired source/results retained separately.",
            "replay":"Every named, convergence and MC C++ run repeated; raw summary and trace bytes identical.",
            "scope":"Synthetic planar educational simulation; endpoint observations, not continuous safety or hardware validation."}
    (outdir/"results.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"checks":len(checks),"aggregate":counts,"convergence":convergence},indent=2),flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--binary",required=True);p.add_argument("--output",required=True);args=p.parse_args()
    run_suite(Path(args.binary).resolve(),Path(args.output))
