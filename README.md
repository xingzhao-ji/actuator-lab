# Actuator Lab

A C++20 reaction-wheel/motor simulator with independent numerical references, sampled controllers, actuator faults and reproducible experimental evidence. The model and every retained trial are synthetic; no hardware was used.

Open **[the self-contained scientific report](evidence/report.html)** for the plots and all named-case outcomes. Equations, units and physical limits are in [the derivation](docs/derivation.md). [Frozen inputs](evidence/frozen-inputs.json), [all measured outcomes](evidence/results.json) and [verification log](evidence/final-checks.txt) accompany the report.

## What was executed

- A nine-state RK4 system: body angle, absolute body/wheel speeds, inductor current, and five stage-consistent work/impulse quadratures.
- Analytic electrical/friction/external-torque limits, exact momentum/energy identities, a separate reduced-coordinate DOP853 solver, and an affine matrix-exponential oracle.
- Smooth convergence at a preselected 0.025 s horizon: scaled state error `1.5447e-8` at default 0.0005 s; successive halving shows approximately fourth-order state/work-balance convergence.
- Seven named scenarios × three controllers, with all 21 plant trajectories independently replayed. Separate closed-loop reference checks cover nominal/pulse controllers.
- 64 frozen parameter/initial-condition trials per controller, with all outcomes retained. Direct voltage PD: **0/64**; cascaded current feedback: **64/64**; conventional feedforward follow-up: **10/64**. Every C++ run is repeated and raw trace/summary hashes checked.
- 27 C++ tests, 32 Python tests, core/simulation ASan+UBSan checks and 121 experiment gates in the current implementation. Final log and manifest record the actual verification run.

The original direct/cascade sweep was frozen before outcomes. A wheel carrying momentum needs nonzero back-EMF compensation even at zero body-angle error; the direct controller therefore has a predictable offset and is not an optimized conventional baseline. After observing that result, the **explicitly post-observation** feedforward ablation retained the same nominal compensation, demand clamp and supervisor as the cascade, but removed proportional/integral current feedback (`Kc=KI=0`). Inputs, gains and parameters were not retuned/resampled. The original paired source and results are [preserved](evidence/checkpoints/original-paired/checkpoint.json); current baseline output hashes match them exactly.

These are deterministic synthetic experiments, not field reliability estimates or a novel-controller claim. Cascade success in the declared sweep coexists with failure under sustained torque, voltage loss, stuck drive and increased bearing drag. A soft speed gate cannot unload total angular momentum or guarantee a continuous-time safety invariant.

## Build and test a standalone checkout

Requirements: C++20 Clang, Python 3.12, and `make`. Historical experiments and the publication tests used macOS/Apple Silicon. Linux and Windows have not been verified. Runtime libraries are installed separately; no virtual environment or executable is shipped.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r requirements.txt
make test sanitize
```

This runs 27 C++ tests, 32 Python tests and core/simulation ASan+UBSan checks without regenerating the historical experiment. The November 2026 publication check used a fresh isolated Python 3.12 environment and a separate build cache; it did not rerun the full 213-case review or experiment sweep. See [publication checks](evidence/publication-checks.txt).

Builds default to `~/.cache/actuator-lab`. Override both through `make CACHE=/absolute/cache/path`; the Makefile exports that location to all subprocesses. The existing resource guard limits that cache to 200 MiB and requires more than 2 GiB host free space. The virtual environment is separate. Use up to four numerical threads, for example `OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 make test`.

For a complete new experiment run, work in a separate disposable checkout so the bundled historical evidence remains available:

```sh
make plots
make verify
```

`make plots` inspects pinned binary-wheel metadata/sizes and installs plotting wheels into the scoped cache. The full `make verify` regenerates `evidence/results.json`, plots, report and manifest in that checkout. It may exceed the time needed by routine tests and was **not** run for this publication. The frozen input file refuses different draws; all completed, tripped and aborted outcomes remain in the denominator. Historical results, traces and figures in this repository came from the October 2026 accepted run, not this packaging check. [Evidence provenance](evidence/README.md) explains the retained original manifests and review probe.

## Run a case

The output must be a new directory with an existing parent. CSV and JSON are written to a temporary sibling and published together by directory rename. Existing outputs are preserved; no durability-after-power-loss claim is made.

```sh
~/.cache/actuator-lab/build/actuator_lab simulate \
  --scenario pulse --controller cascaded --output /tmp/actuator-pulse
```

| Option | Meaning |
|---|---|
| `--scenario` | `nominal`, `pulse`, `bias`, `sustained`, `zero_voltage`, `stuck_positive`, `drag`, `fixed` |
| `--controller` | `direct`, `cascaded`, `feedforward` |
| `--ticks`, `--Tc`, `--substeps` | Integer intervals, controller seconds, RK4 steps per interval; defaults 2000/0.01/20 |
| `--Jb`, `--Jw`, `--R`, `--L`, `--k`, `--b` | Physical parameters, SI units as in derivation |
| `--theta0`, `--wb0`, `--ww0`, `--i0` | Initial unwrapped angle, absolute angular rates and current |
| `--target` | Target angle in radians, default π/6 |
| `--pulse` | Scheduled external torque in N m, default 0.01 |
| `--fixed-voltage`, `--external` | Constant forcing for open-loop `fixed` numerical experiments |
| `--fault-voltage`, `--drag-multiplier` | Stuck-driver voltage and scheduled bearing multiplier |

The bias/drag defaults start with `omega_w=120 rad/s`; sustained torque runs 30 s. Explicit initial/tick options override these defaults. All event times and Monte Carlo ranges are in frozen-inputs.json. Controller sampling must divide one second, so all known second-aligned event times become exact integer tick boundaries.

Exit status is 0 for completed experiments (including physical failure to settle), 2 for invalid config/publication failures, and 3 for numerical-envelope abort with a clearly failed diagnostic artifact. Always inspect `success`, `tripped`, `excursion` and `aborted`; process completion alone is not experimental success. Terminal maxima include all RK substep endpoints in the last 2 s, not only saved controller samples. The final CSV input/command row describes the terminal boundary; no interval is integrated after it.

Parameters and forcing are finite and bounded. CLI limits include a 120 s horizon, 250,000 sample intervals, 1–1000 substeps, 5,000,000 integration steps and a step-size admission rule incorporating electrical, mechanical and scheduled-drag time scales. See [design](docs/design.md) for complete bounds. Physical states are never clipped; a numerical-envelope violation retains the last admissible state and stops.

## Scope and learning

The model uses linear resistance/inductance/back EMF, relative viscous friction and a common axis. It excludes 3D attitude dynamics, switching electronics, temperature-dependent parameters, field/finite-element EM, sensor estimation/noise, physical I/O and flight certification. Zero voltage means closed terminals, not an open circuit. A stuck driver overrides the commanded safety inhibit.

AI-assisted source/evidence does not establish personal expertise. To make this useful in interviews, independently derive the power cancellation, explain why wheel bias causes direct-controller offset, reproduce one failed case, and change a physical assumption while preserving independently checked invariants. The project can support a bounded claim about implementing and verifying an electromechanical simulation once you can explain and maintain it.

[Design](docs/design.md) · [accepted scope and deviations](docs/acceptance-addendum.md) · [independent AI-assisted review](docs/independent-employer-review.md) · [publication provenance](docs/publication-provenance.json)

The review was performed by a separate AI agent, not an employer or certification body. No project license has been added. External libraries retain their own terms; the notice for DejaVu font subsets embedded in the generated PDFs is included in [third-party notices](THIRD_PARTY_NOTICES.md).

## Original measurement completion — November 2026

The [additive measurement report](evidence/metrics-v2/report.html) completes the
original settling-time, duration-weighted gate-occupancy, and separate gross
terminal supply/regeneration measurements. On November 7 UTC (November 6 local),
all **213 fixed configurations** reproduced every historical legacy summary field
and CSV hash exactly. Nine independent absolute-coordinate DOP853 comparisons and
33 four-times-substep sensitivity cases passed the unchanged prescribed limits.
[Definitions and numerical results](docs/metrics-v2.md),
[all 213 rows](evidence/metrics-v2/runs.csv), and the
[artifact manifest](evidence/metrics-v2/manifest.json) retain the audit trail.

The original October experiment and its negative outcomes remain unchanged:
Monte Carlo success is direct **0/64**, cascaded **64/64**, feedforward **10/64**.
The new tracking-settling counts happen to match those counts on this cohort;
the metrics have separate definitions. Feedforward remains a post-observation
ablation. These endpoint-observed synthetic measurements do not establish
continuous-time safety, hardware performance, battery recovery efficiency, or
personal mastery. Historical compiler identity was observed after Task1 builds;
the tested binary was hash-pinned for the new replay, without claiming earlier
compiler provenance. This agent-assisted extension remains subject to independent
artifact review and separate publication checks.
