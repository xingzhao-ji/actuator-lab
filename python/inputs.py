"""Inputs are generated and frozen before reading any comparative outcomes."""
import hashlib
import json
from pathlib import Path
import numpy as np

RANGES={"Jb":[.035,.065],"Jw":[.0007,.0013],"R":[1.5,2.5],"L":[.008,.012],"k":[.04,.06],"b":[.000005,.000015],"theta0":[-.1,.1],"wb0":[-.01,.01],"ww0":[-100,100],"target":[-.5,.5],"pulse":[-.005,.005]}
CASES=["nominal","pulse","bias","sustained","zero_voltage","stuck_positive","drag"]

def freeze(path):
    rng=np.random.Generator(np.random.PCG64(20261023))
    trials=[{"id":n,"options":{"scenario":"pulse","ticks":2000,"substeps":20,"Tc":.01,"i0":0,**{key:float(rng.uniform(*bounds)) for key,bounds in RANGES.items()}}} for n in range(64)]
    record={"schema_version":1,"seed":20261023,"generator":"NumPy PCG64 independent uniform, fixed draw order","ranges":RANGES,"count":64,"trials":trials,
            "named_cases":CASES,"defaults":{"Tc":.01,"substeps":20,"target":float(np.pi/6),"ticks":2000,"sustained_ticks":3000,"bias_and_drag_ww0":120,"pulse_torque":.01,"pulse_seconds":[6,7],"sustained_start":2,"zero_voltage_start":6,"zero_voltage_disturbance_seconds":[8,12],"stuck_voltage_start":4,"stuck_voltage":12,"drag_start":4,"drag_multiplier":30},
            "smooth_convergence":{"Tc":.001,"ticks":25,"substeps":[1,2,4],"voltage":1,"external_torque":.003,"initial":[0]*9}}
    encoded=(json.dumps(record,indent=2,sort_keys=True)+"\n").encode()
    path=Path(path);path.parent.mkdir(exist_ok=True,parents=True)
    if path.exists() and path.read_bytes()!=encoded:raise RuntimeError("frozen inputs differ; refusing replacement")
    if not path.exists():path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()

if __name__=="__main__":
    import sys
    print(freeze(sys.argv[1]))
