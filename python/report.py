"""Publication-style static figures and a portable, self-contained HTML report."""
import base64
import gzip
import html
import io
import json
import os
from pathlib import Path
import sys
cache=Path(os.environ.get("ACTUATOR_CACHE",Path.home()/".cache/job-apps-runtime/actuator-lab"))
sys.path.insert(0,str(cache/"plot-site"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

COLORS={"direct":"#d26926","cascaded":"#246c96","feedforward":"#5c7a38"}

def render_report(outdir):
    out=Path(outdir);r=json.loads((out/"results.json").read_text());figdir=out/"figures";figdir.mkdir(exist_ok=True)
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False,"axes.grid":True,"grid.alpha":.2,"savefig.dpi":160,"pdf.fonttype":42})
    images=[]
    def trace(case,kind):return np.genfromtxt(io.BytesIO(gzip.decompress((out/"traces"/f"{case}-{kind}.csv.gz").read_bytes())),delimiter=",",names=True)
    def save(fig,name,caption):
        # Resolve all layout/text before export; avoid a second tight-bbox crop pass.
        fig.canvas.draw()
        fig.savefig(figdir/f"{name}.png");fig.savefig(figdir/f"{name}.pdf");plt.close(fig);images.append((name,caption))
    for cases,name,title in [(["pulse","stuck_positive"],"response","A recoverable pulse and an uncommandable stuck driver"),(["sustained","drag"],"limits","Failure envelopes: finite momentum capacity and unmodeled drag")]:
        fig,axes=plt.subplots(3,2,figsize=(12,8.5),sharex="col")
        fig.subplots_adjust(left=.13,right=.98,bottom=.08,top=.90,hspace=.24,wspace=.25)
        for column,case in enumerate(cases):
            for kind,color in COLORS.items():
                t=trace(case,kind);axes[0,column].plot(t["time"],t["theta"],color=color,label=kind)
                axes[1,column].plot(t["time"],t["current"],color=color)
                axes[2,column].plot(t["time"],t["omega_wheel"]-t["omega_body"],color=color)
            axes[0,column].axhline(np.pi/6,color="black",ls=":",lw=1,label="target")
            for v in [-2.5,2.5]:axes[1,column].axhline(v,color="black",ls="--",lw=.8,label="hard current limit" if v>0 else None)
            for v in [-200,200]:axes[2,column].axhline(v,color="black",ls="--",lw=.8,label="hard speed limit" if v>0 else None)
            for v in [-150,150]:axes[2,column].axhline(v,color="gray",ls=":",lw=.8,label="soft speed gate" if v>0 else None)
            axes[0,column].set_title(case.replace("_"," "));axes[2,column].set_xlabel("Time (s)")
        for row,label in enumerate(["Body angle (rad)","Motor current (A)","Relative wheel speed (rad/s)"]):axes[row,0].set_ylabel(label)
        axes[1,1].legend(loc="lower right",fontsize=8);axes[2,1].legend(loc="lower right",fontsize=8)
        axes[0,0].legend(loc="best");fig.suptitle(title,fontsize=14)
        save(fig,name,"Synthetic trajectories. Dashed limits: sampled hard trip at 2.5 A and 200 rad/s; dotted speed lines: 150 rad/s soft command gate. These gates do not guarantee continuous safety or recovery from a stuck voltage driver.")
    t=trace("pulse","cascaded");p=r["named"][1]["cascaded"]["config"]["plant"]
    E=.5*(p["Jb"]*t["omega_body"]**2+p["Jw"]*t["omega_wheel"]**2+p["L"]*t["current"]**2);E-=E[0]
    net=t["W_e"]-t["Q_R"]-t["Q_b"]+t["W_ext"]
    fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True,layout="constrained")
    for field,label in [("W_e","Electrical input"),("Q_R","Copper loss"),("Q_b","Bearing loss"),("W_ext","External body work")]:axes[0].plot(t["time"],t[field],label=label)
    axes[0].plot(t["time"],E,"k--",label="Stored energy change");axes[0].set_ylabel("Energy / work (J)");axes[0].legend(ncols=2)
    axes[1].plot(t["time"],E-net,color=COLORS["cascaded"]);axes[1].set_ylabel("Work-balance defect (J)");axes[1].set_xlabel("Time (s)")
    fig.suptitle("Energy accounting includes external torque work",fontsize=14)
    save(fig,"energy","Pulse case, cascaded controller. Every work quadrature uses the same RK4 stages as the physical states. Electrical work is signed; resistance and relative-bearing terms dissipate energy. Defect is numerical error, not missing external work.")
    c=r["convergence"];h=np.array([v["h"] for v in c]);fig,axes=plt.subplots(1,2,figsize=(10,4),layout="constrained")
    for ax,key,ylabel in zip(axes,["state_error","max_energy_defect"],["Scaled state error","Maximum work-balance defect (J)"]):
        values=np.array([v[key] for v in c]);ax.loglog(h,values,"o-",color=COLORS["cascaded"],label="Measured");ax.loglog(h,values[0]*(h/h[0])**4,"k--",label="h⁴ guide");ax.set_xlabel("RK4 step h (s)");ax.set_ylabel(ylabel);ax.legend()
    fig.suptitle("Smooth fixed-input convergence at preselected t = 0.025 s",fontsize=13)
    save(fig,"convergence","State oracle: affine matrix exponential in total momentum/relative speed coordinates. DOP853 independently checks that oracle and work ledgers. State scales are 1 rad, 1 rad/s, 100 rad/s and 1 A. Fourth-order behavior is asserted only for this smooth experiment, not hybrid saturation/trip transitions.")
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout="constrained")
    for kind,color in COLORS.items():
        a=np.array([t[kind]["terminal_angle_error"] for t in r["monte_carlo"]]);w=np.array([t[kind]["terminal_body_speed"] for t in r["monte_carlo"]]);passed=np.array([t[kind]["success"] for t in r["monte_carlo"]])
        if (~passed).any():axes[0].scatter(a[~passed],w[~passed],marker="x",color=color,label=f"{kind}: failed criterion")
        if passed.any():axes[0].scatter(a[passed],w[passed],marker="o",s=18,color=color,label=f"{kind}: passed")
    axes[0].axvline(.01,color="black",ls="--",lw=.8);axes[0].axhline(.002,color="black",ls="--",lw=.8)
    axes[0].set_xscale("log");axes[0].set_yscale("log");axes[0].set_xlabel("Last 2 s maximum |angle error| (rad)");axes[0].set_ylabel("Last 2 s maximum |body rate| (rad/s)");axes[0].legend(fontsize=8)
    counts=[r["aggregate"][f"{k}_success"] for k in COLORS];axes[1].bar(list(COLORS),counts,color=list(COLORS.values()));axes[1].set_ylim(0,70);axes[1].set_ylabel("Successful trials / 64 frozen inputs")
    for n,value in enumerate(counts):axes[1].text(n,value+1,f"{value}/64",ha="center")
    fig.suptitle("Paired parameter/initial-state sweep — all trials retained",fontsize=14)
    save(fig,"monte-carlo","Independent uniform draws, NumPy PCG64 seed 20261023, 64 shared inputs with fixed nominal gains. Feedforward is a post-observation ablation of current feedback, using unchanged inputs. Passing additionally requires no sampled trip, observed hard-limit excursion or numerical abort. This designed synthetic range is not a field reliability population or a comparison with an optimally tuned direct controller.")
    rows=[]
    for pair in r["named"]:
        for kind in COLORS:
            s=pair[kind];reason="PASS" if s["success"] else "FAIL: "+("numerical abort" if s["aborted"] else "sampled trip" if s["tripped"] else "hard excursion" if s["excursion"] else "terminal settling")
            rows.append(f"<tr><td>{pair['scenario']}</td><td>{kind}</td><td>{reason}</td><td>{s['terminal_angle_error']:.4g}</td><td>{s['terminal_body_speed']:.4g}</td><td>{s['max_current']:.4g}</td><td>{s['max_relative_speed']:.4g}</td></tr>")
    figures="".join(f'<figure><img alt="{html.escape(caption)}" src="data:image/png;base64,{base64.b64encode((figdir/(name+".png")).read_bytes()).decode()}"><figcaption>{html.escape(caption)} <a href="figures/{name}.pdf">Vector PDF</a></figcaption></figure>' for name,caption in images)
    maxref=max(v["plant_replay_scaled_state_error"] for v in r["reference_checks"])
    text=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Actuator Lab · numerical evidence</title><style>body{{max-width:1120px;margin:40px auto;padding:0 24px;font:16px/1.55 system-ui;color:#172631;background:#fff}}h1{{font-size:38px;line-height:1.15}}h2{{margin-top:36px}}p{{max-width:900px}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{padding:9px 8px;border-bottom:1px solid #d3dce0;text-align:left}}th{{background:#edf2f4}}figure{{margin:36px 0}}img{{width:100%;height:auto}}figcaption{{font-size:14px;color:#425562}}code{{font-size:13px;overflow-wrap:anywhere}}.note{{border-left:4px solid #246c96;padding:12px 18px;background:#f2f6f8}}.scroll{{overflow:auto}}</style>
<h1>Actuator Lab</h1><p>One-axis reaction-wheel dynamics, controller comparison and independently checked numerical evidence.</p>
<p class="note"><strong>Observed outcome:</strong> cascaded current control passed {r['aggregate']['cascaded_success']}/64 frozen trials; direct voltage feedback passed {r['aggregate']['direct_success']}/64. The post-observation feedforward ablation passed {r['aggregate']['feedforward_success']}/64 on those unchanged inputs. All use the same outer gains and initial conditions. These synthetic parameters are educational assumptions, with no manufacturer fit or physical validation.</p>
<h2>What the experiment measures</h2><p>The C++20 plant evolves body angle, absolute body and wheel speeds, and motor current. Back EMF and bearing loss depend on <em>relative</em> speed. One SI motor constant enforces torque/back-EMF consistency. Five work/impulse ledgers share the same fourth-order Runge–Kutta stages. Terminal success means the entire last two seconds has |angle error| ≤ 0.01 rad and |body rate| ≤ 0.002 rad/s, with no trip, observed hard-limit excursion or abort.</p>
<p>The cascade compensates nominal back EMF and adds current feedback with conditional integration. The baseline has no back-EMF/current compensation and is not claimed optimally tuned. Its missing back-EMF term forces a steady angle offset when the wheel has stored momentum; a nominal 0.01 N m s pulse predicts the observed 0.105 rad offset. The follow-up feedforward controller keeps the cascade’s current-demand clamp and nominal compensation but removes proportional/integral current feedback (Kc=KI=0). It was added after observing the original results; no inputs were resampled and no gains retuned. Original paired source/results are preserved in checkpoints/original-paired. The soft speed gate cannot unload total angular momentum; sustained external torque ultimately defeats attitude regulation. Zero commanded voltage models closed motor terminals, not an open circuit. A stuck driver can override the safety command.</p>
<h2>Verification</h2><p>{len(r['checks'])} executed numerical/experiment gates passed. Every C++ experiment was replayed with identical raw trace and summary bytes. Twenty-one named trajectories were separately integrated with SciPy DOP853 in total-momentum/relative-speed coordinates; maximum scaled physical-state difference was {maxref:.3g}. Independent closed-loop commands were also compared for nominal and pulse cases. The smooth h = 0.0005 s error was {r['convergence'][1]['state_error']:.3g}; three step sizes show fourth-order state/work-balance convergence. Tightening the reference tolerance passed its sensitivity check.</p>
<p>Checks cover analytical electrical, friction and external-torque limits, momentum/energy identities, event boundaries, trips/faults, strict CLI admission, failure publication and failed-trial retention. ASan/UBSan and unit/CLI results are recorded separately in final-checks.txt. Maxima are observed at RK substep endpoints; this is not a continuous-time safety proof.</p>
{figures}
<h2>All named-case outcomes</h2><div class="scroll"><table><thead><tr><th>Case</th><th>Controller</th><th>Outcome</th><th>Terminal angle error (rad)</th><th>Terminal rate (rad/s)</th><th>Peak |i| (A)</th><th>Peak |relative speed| (rad/s)</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h2>Reproduction and provenance</h2><p>Run <code>make verify</code> from the project after installing isolated plotting wheels with <code>make plots</code>. See <a href="../README.md">README</a>, <a href="../docs/derivation.md">derivation</a>, <a href="frozen-inputs.json">all frozen inputs/ranges</a> and <a href="results.json">all outcomes, reference errors and source hashes</a>. The HTML embeds every plot and remains readable when copied by itself; linked PDFs/data require the evidence folder.</p><p>Frozen input SHA-256: <code>{r['input_sha256']}</code><br>Executable SHA-256: <code>{r['binary_sha256']}</code></p>
<p>Deliberately excluded: 3D spacecraft dynamics, magnetic-field simulation, switching electronics, thermal failure, sensor noise/estimation, hardware timing, desaturation actuators, flight certification and proof of personal mastery. The source and retained failure cases are material for learning and technical review.</p></html>'''
    (out/"report.html").write_text(text)
    print(f"Rendered {len(images)} PNG/PDF figures and self-contained report.html")

if __name__=="__main__":render_report(sys.argv[1])
