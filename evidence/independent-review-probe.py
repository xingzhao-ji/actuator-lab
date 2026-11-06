"""Fresh review probes: no project plant/controller/reference implementation imported.

Run from project root with the existing ModelGate Python. Runtime stays in the
dedicated review cache. This file is review evidence, not production test code.
"""
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time

import numpy as np
from scipy.linalg import expm

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path.home() / ".cache/job-apps-runtime/actuator-lab/independent-review"
BINARY = CACHE / "build/actuator_lab"
FIELDS = "theta omega_body omega_wheel current W_e Q_R Q_b W_ext I_ext".split()
KINDS = ("direct", "cascaded", "feedforward")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def invoke(options, read_trace=False):
    with tempfile.TemporaryDirectory(dir=CACHE / "tmp", prefix="review-") as tmp:
        out = Path(tmp) / "run"
        args = [str(BINARY), "simulate", "--output", str(out)]
        for key, value in options.items():
            args.extend(["--" + key, str(value)])
        proc = subprocess.run(args, capture_output=True, text=True, timeout=30)
        assert proc.returncode in (0, 3), proc.stderr
        sb = (out / "summary.json").read_bytes()
        tb = (out / "trace.csv").read_bytes()
        s = json.loads(sb)
        assert s["aborted"] == (proc.returncode == 3)
        trace = np.genfromtxt(io.BytesIO(tb), names=True, delimiter=",") if read_trace else None
        return s, trace, sha(sb), sha(tb)


def oracle(x, p, voltage, external, duration, multiplier=1):
    """Absolute-coordinate affine system + exact second-moment work propagation.

    y=[theta, wb, ww, i, 1]. The 25 entries of yy^T obey a linear
    Kronecker-sum system. Five appended integrals make each work/impulse
    quantity an independent matrix-exponential result, without RK stages,
    DOP853, or the project's reduced-coordinate reference.
    """
    jb, jw, resistance, inductance, k, b = (p[n] for n in ("Jb", "Jw", "R", "L", "k", "b"))
    b *= multiplier
    a = np.zeros((5, 5))
    a[0, 1] = 1
    a[1] = [0, -b/jb, b/jb, -k/jb, external/jb]
    a[2] = [0, b/jw, -b/jw, k/jw, 0]
    a[3] = [0, k/inductance, -k/inductance, -resistance/inductance, voltage/inductance]
    lifted = np.zeros((30, 30))
    lifted[:25, :25] = np.kron(a, np.eye(5)) + np.kron(np.eye(5), a)
    power = np.zeros((5, 5, 5))
    power[0, 3, 4] = power[0, 4, 3] = voltage/2
    power[1, 3, 3] = resistance
    power[2, 1, 1] = power[2, 2, 2] = b
    power[2, 1, 2] = power[2, 2, 1] = -b
    power[3, 1, 4] = power[3, 4, 1] = external/2
    power[4, 4, 4] = external
    lifted[25:, :25] = power.reshape(5, 25)
    y = np.r_[x[:4], 1.]
    state = np.r_[np.outer(y, y).ravel(), x[4:]]
    z = expm(lifted * duration) @ state
    return np.r_[z[:25].reshape(5, 5)[:4, 4], z[25:]]


def main():
    started = time.monotonic()
    evidence = ROOT / "evidence"
    r = json.loads((evidence / "results.json").read_text())
    frozen = json.loads((evidence / "frozen-inputs.json").read_text())
    manifest = json.loads((evidence / "manifest.json").read_text())
    old = json.loads((evidence / "checkpoints/original-paired/results.json").read_text())
    for path, record in manifest["source_and_evidence"].items():
        data = (ROOT / path).read_bytes()
        assert sha(data) == record["sha256"] and len(data) == record["bytes"], path
    for path, digest in r["source_sha256"].items():
        assert sha((ROOT / path).read_bytes()) == digest, path
    assert sha((evidence / "frozen-inputs.json").read_bytes()) == r["input_sha256"] == old["input_sha256"]
    with tarfile.open(evidence / "checkpoints/original-paired/source.tar.gz") as archive:
        assert set(archive.getnames()) == set(old["source_sha256"])
        for member in archive.getmembers():
            assert sha(archive.extractfile(member).read()) == old["source_sha256"][member.name]
    for group in ("named", "monte_carlo"):
        for before, after in zip(old[group], r[group], strict=True):
            for kind in KINDS[:2]:
                for field in ("summary_sha256", "trace_sha256"):
                    assert before[kind][field] == after[kind][field]
    assert len(r["checks"]) == 121 and all(x["passed"] for x in r["checks"])
    print("PASS current manifest, all original archive members, frozen input and original paired hashes", flush=True)

    replay_count = 0
    for named in r["named"]:
        for kind in KINDS:
            _, _, summary_sha, trace_sha = invoke({"scenario": named["scenario"], "controller": kind})
            assert summary_sha == named[kind]["summary_sha256"]
            assert trace_sha == named[kind]["trace_sha256"]
            replay_count += 1
    outcomes = {kind: 0 for kind in KINDS}
    for trial, expected in zip(frozen["trials"], r["monte_carlo"], strict=True):
        assert trial["id"] == expected["id"]
        for kind in KINDS:
            s, _, summary_sha, trace_sha = invoke({**trial["options"], "controller": kind})
            assert summary_sha == expected[kind]["summary_sha256"]
            assert trace_sha == expected[kind]["trace_sha256"]
            outcomes[kind] += int(s["success"])
            replay_count += 1
    print(f"PASS fresh-binary exact raw replay of {replay_count} cases; outcomes {outcomes}", flush=True)

    # Independent new signed/biased fixtures, no alteration to frozen experiment.
    rng = np.random.default_rng(20261024)
    smooth = []
    for index in range(32):
        p = {name: float(rng.uniform(*frozen["ranges"][name])) for name in ("Jb", "Jw", "R", "L", "k", "b")}
        if index % 8 == 0:
            p["b"] = 0.
        x = np.r_[rng.uniform(-.2,.2), rng.uniform(-.2,.2), rng.uniform(-120,120), rng.uniform(-2,2), np.zeros(5)]
        voltage, external = float(rng.uniform(-12,12)), float(rng.uniform(-.05,.05))
        exact = oracle(x, p, voltage, external, .025)
        options = {"scenario": "fixed", "Tc": .001, "ticks": 25, "fixed-voltage": voltage, "external": external,
                   "theta0": x[0], "wb0": x[1], "ww0": x[2], "i0": x[3], **p}
        errors = []
        for steps in (2, 8):
            _, trace, _, _ = invoke({**options, "substeps": steps}, True)
            actual = np.array([trace[name][-1] for name in FIELDS])
            delta = abs(actual - exact)
            errors.append({"scaled_state": float(max(delta[:4]/[1,1,100,1])), "work_J": float(max(delta[4:8])), "impulse_Nms": float(delta[8])})
        assert errors[0]["scaled_state"] < 1e-5 and errors[0]["work_J"] < 1e-5
        assert errors[1]["scaled_state"] < 1e-7 and errors[1]["work_J"] < 1e-7
        assert errors[1]["scaled_state"] < errors[0]["scaled_state"]/100
        assert errors[1]["work_J"] < errors[0]["work_J"]/100
        smooth.append({"id": index, "config": options, "h_0.0005": errors[0], "h_0.000125": errors[1]})
    print("PASS 32 new absolute-coordinate/second-moment state and work oracle cases at two resolutions", flush=True)

    # Explicitly inspect both sides of every scenario discontinuity.
    edge_rows = []
    for named in r["named"]:
        case = named["scenario"]
        boundaries = {"pulse": [600,700], "zero_voltage": [600,800,1200], "stuck_positive": [400], "drag": [400], "sustained": [200]}.get(case, [])
        for kind in KINDS:
            trace = np.genfromtxt(io.BytesIO(gzip.decompress((evidence / "traces" / f"{case}-{kind}.csv.gz").read_bytes())), names=True, delimiter=",")
            assert named[kind]["max_current"] + 1e-12 >= max(abs(trace["current"]))
            assert named[kind]["max_relative_speed"] + 1e-12 >= max(abs(trace["omega_wheel"]-trace["omega_body"]))
            for tick in boundaries:
                for left in (tick-1, tick):
                    x = np.array([trace[name][left] for name in FIELDS])
                    exact = oracle(x, named[kind]["config"]["plant"], trace["voltage"][left], trace["external_torque"][left], .01, trace["bearing_multiplier"][left])
                    actual = np.array([trace[name][left+1] for name in FIELDS])
                    delta = abs(actual - exact)
                    se, we = float(max(delta[:4]/[1,1,100,1])), float(max(delta[4:8]))
                    assert se < 2e-6 and we < 2e-5
                    edge_rows.append({"case": case, "controller": kind, "left_tick": left, "scaled_state_error": se, "work_error_J": we})
    print(f"PASS {len(edge_rows)} left/right event intervals against independent oracle", flush=True)

    # Resolution sensitivity of decisions across every original MC input.
    refinement = []
    for trial, expected in zip(frozen["trials"], r["monte_carlo"], strict=True):
        for kind in KINDS:
            s, _, _, _ = invoke({**trial["options"], "controller": kind, "substeps": 80})
            baseline = expected[kind]
            for flag in ("success", "tripped", "aborted", "excursion"):
                assert s[flag] == baseline[flag], (trial["id"], kind, flag)
            refinement.append({"id": trial["id"], "controller": kind,
                               "angle_delta_rad": abs(s["terminal_angle_error"]-baseline["terminal_angle_error"]),
                               "rate_delta_rad_s": abs(s["terminal_body_speed"]-baseline["terminal_body_speed"])})
    print("PASS all 192 MC outcome/limit flags unchanged with four times finer RK steps", flush=True)
    result = {"status": "passed", "reviewer": "fresh independent agent", "method": "No project simulation or reference implementation imported",
              "original_manifest_sha256": sha((evidence/"manifest.json").read_bytes()), "results_sha256": sha((evidence/"results.json").read_bytes()),
              "review_binary_sha256": sha(BINARY.read_bytes()), "manifest_files_verified": len(manifest["source_and_evidence"]),
              "archived_source_files_verified": len(old["source_sha256"]), "fresh_binary_exact_replays": replay_count,
              "outcomes": outcomes, "new_oracle_cases": smooth, "event_interval_checks": edge_rows, "mc_refinement": refinement,
              "elapsed_seconds": time.monotonic()-started}
    (evidence/"independent-review-results.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("new_oracle_cases", "event_interval_checks", "mc_refinement")}, indent=2))


if __name__ == "__main__":
    main()
