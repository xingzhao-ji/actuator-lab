# Actuator Lab design — one-axis electromechanical control

## Purpose and scope

Build an executed C++20 numerical ODE and electromechanical modeling experiment. Expose assumptions and failed operating regimes. This is the original technical design, with standalone packaging wording; the [acceptance addendum](acceptance-addendum.md) distinguishes delivered metrics from the original plan.

The artifact is a single-axis rigid body carrying one coaxial reaction wheel driven by an idealized brushed-DC-equivalent actuator. It includes winding inductance, resistance, back EMF, equal-and-opposite motor/bearing torque, sampled controllers, voltage saturation, supervisory gates, deliberate faults and an external disturbance torque. Parameters are synthetic educational values, not measured or validated hardware specifications. No flight-grade, hardware-in-loop, spacecraft-fidelity, reinforcement-learning or general electromagnetism-mastery claim follows.

Three alternatives were considered: a pure software animation would not establish numerical correctness; a full three-axis/flight stack would add unvalidated geometry and hardware complexity; the selected one-axis coupled electrical/mechanical model supports independent analytic, conservation and integration checks with manageable assumptions.

## Coordinates, model and sources

Use one inertial axis, positive for both wheel and body rotation. States are unwrapped body angle `theta_b` [rad], body absolute angular velocity `omega_b` [rad/s], wheel absolute angular velocity `omega_w` [rad/s] and winding current `i` [A]. The motor stator and bearing are attached to the body. Rotor speed relative to the stator is `r = omega_w - omega_b`; it is `r`, not absolute wheel speed, that produces back EMF and bearing friction. `J_b` excludes the wheel's spin inertia; `J_w` is the wheel's inertia about the same axis. Inertia is constant; translational motion, cross-axis coupling, gyroscopic terms and gravitational potential are outside this model.

With positive terminal voltage `V`, external torque `tau_ext` applied to the body, and positive motor torque accelerating the wheel:

```text
theta_b' = omega_b
i'       = (V - R*i - k*r) / L
tau      = k*i - b*r
omega_w' = tau / J_w
omega_b' = (tau_ext - tau) / J_b
```

`R` [ohm], `L` [H], `k_t` [N m/A], `k_e` [V s/rad], `b` [N m s/rad], and inertias [kg m²] give consistent dimensions. The model accepts one SI constant `k`, used for both `k_t` and `k_e`; mismatched constants cannot be supplied. Ideal electromechanical conversion then has power `k*i*r` on both sides. The [University of Michigan motor model](https://ctms.engin.umich.edu/CTMS/?example=MotorPosition&section=SimulinkSimscape) and [maxon's motor-modeling explanation](https://support.maxongroup.com/hc/en-us/articles/360013761160-Motor-data-and-simulation) support this SI convention. The wheel/body distinction and need for external momentum unloading follow [NASA's attitude-control explanation](https://science.nasa.gov/learn/basics-of-space-flight/chapter11-2/) and [reaction-wheel saturation discussion](https://www.nasa.gov/smallsat-institute/sst-soa/guidance-navigation-and-control/). The equations and checks below are derived for this project's stated coordinates, not attributed to a particular spacecraft.

### Independent conservation derivation

Total angular momentum is `H = J_b*omega_b + J_w*omega_w`, so `H' = tau_ext`; internal motor and bearing torques cancel.

Stored energy is `E = (J_b*omega_b² + J_w*omega_w² + L*i²)/2`. Differentiating gives

```text
E' = omega_b*(tau_ext-tau) + omega_w*tau + i*(V-R*i-k*r)
   = V*i - R*i² - b*r² + tau_ext*omega_b.
```

The external-work term is essential. Omitting that term is valid only when external mechanical power vanishes. No mechanical/current state will be projected or clipped to improve this balance.

Augment the four physical states with five integrated quantities: electrical work `W_e'=V*i`, resistive loss `Q_R'=R*i²`, bearing loss `Q_b'=b*r²`, external work `W_ext'=tau_ext*omega_b`, and external angular impulse `I_ext'=tau_ext`. Integrate all nine states with the same RK4 stages. Report `E-E0-W_e+Q_R+Q_b-W_ext` and `H-H0-I_ext`, both absolute and scaled. Electrical work may be negative under regeneration; losses must be nonnegative.

### Different-coordinate reference

The SciPy reference independently evolves `[theta_b,H,r,i]`, with `J_eff=J_b*J_w/(J_b+J_w)`:

```text
H'       = tau_ext
r'       = (k*i-b*r)/J_eff - tau_ext/J_b
i'       = (V-R*i-k*r)/L
theta_b' = (H-J_w*r)/(J_b+J_w)
```

Recover `omega_b=(H-J_w*r)/(J_b+J_w)` and `omega_w=omega_b+r`. This different coordinate system can catch sign/inertia mistakes instead of merely copying the C++ RHS. Use SciPy DOP853 at `rtol=1e-11` with component absolute tolerances at most `1e-12`; repeat selected cases at tighter settings. For piecewise-constant voltage/torque, independently construct the affine matrix and compare physical states with `scipy.linalg.expm`. Work integrals remain independently integrated; no C++ function is called from the reference. [SciPy's solver documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html) distinguishes high-accuracy explicit integration from stiff-system methods.

## Sampling, integration and safety semantics

Default controller interval is 0.01 s; default RK4 has 20 equal substeps per interval (`h=0.0005 s`). Controller outputs are held constant over each interval. Scenario fault/disturbance changes occur on specified controller ticks. Each interval uses its left-side forcing for every RK4 stage, including its right endpoint; the next interval uses the new forcing. This avoids accidentally averaging a discontinuity into an RK4 step. Horizon, controller ticks and substeps use integers, avoiding accumulated floating-point scheduling drift.

Fixed-voltage smooth convergence is a separate experiment from closed-loop/hybrid behavior. Check fourth-order state and work-balance convergence at `h=0.001,0.0005,0.00025 s` against the independent reference, away from roundoff floors. For controller/fault cases, compare trajectories and explicit event records; do not claim fourth-order convergence across changing sampled trip decisions.

Reject nonfinite inputs, missing/duplicate/unknown CLI options, invalid bounds and unresolved time steps before creating final outputs. Require positive `J_b,J_w,R,L,k`, nonnegative `b`, ordered soft/hard limits, and `h <= 0.25*min(L/R, sqrt(L*J_eff)/k, J_eff/b)` (omit the last term when `b=0`). This is a conservative admission rule for the selected explicit solver, not a theorem for every possible controller. Runtime checks also reject nonfinite states or excursions outside the declared numerical envelope. Such runs are recorded as aborted failures; their states are never clipped.

Default illustrative parameters:

| Parameter | Value |
|---|---:|
| `J_b`, `J_w` | 0.05, 0.001 kg m² |
| `R`, `L`, `k`, `b` | 2 ohm, 0.01 H, 0.05 SI, 0.00001 N m s/rad |
| Terminal voltage bound | ±12 V |
| Current command soft bound / measured trip | 2 A / 2.5 A |
| Relative-speed command gate / measured trip | 150 / 200 rad/s |
| Nominal target, duration | pi/6 rad, 20 s |

The outer desired wheel torque is `tau_req=K_p*(theta_b-target)+K_d*omega_b`, with `K_p=0.12 N m/rad`, `K_d=0.16 N m s/rad`. The sign is opposite the desired body torque. Both controllers use the same outer gains and the same sampled hard-trip supervisor:

- **Direct voltage PD baseline:** `V_raw=(R_nom/k_nom)*tau_req`, followed by voltage saturation; no current loop or back-EMF compensation.
- **Cascaded controller:** convert torque to `i_ref=clamp((tau_req+b_nom*r)/k_nom,±2 A)`, then use `V_raw=R_nom*i_ref+k_nom*r+K_c*(i_ref-i)+K_I*z`, with `K_c=0.5 ohm`, `K_I=5 ohm/s` and `z` the sampled current-error integral. Integrate `z` only when voltage is unsaturated or the error would bring it back toward the permitted range. Do not retune gains per Monte Carlo trial.

At the soft speed boundary, a wheel-torque request that would push relative speed farther outward is set to zero before either controller's conversion. This is a conservative command gate, not state clipping or momentum unloading. At a measured hard current/speed breach, latch commanded terminal voltage to zero and freeze the current-loop integrator. The physical model for zero voltage is a closed-terminal/freewheeling circuit, not an ideal open circuit: current stays continuous and regeneration/bearing drag can still transfer momentum. A stuck-voltage fault can override the commanded inhibit; this must be visible as a protection failure. Sampled checks cannot certify that no between-sample threshold crossing occurred. Record maxima at integration substep endpoints and distinguish command gates, detected hard trips and observed limit excursions.

No controller can remove total momentum without external torque. Sustained disturbance and wheel saturation must remain a documented failure envelope, not be hidden by resetting wheel speed or relabeling success.

## Experiments and acceptance evidence

1. **Analytic limits:** decoupled RL circuit (`k=b=0` in a test-only model limit); friction-only momentum exchange with `r(t)=r0*exp(-b*t/J_eff)`; torque-free co-rotation; constant external torque with uncoupled electrical dynamics. These mathematical limits are exposed only in the verification harness; ordinary simulation config retains positive `k`.
2. **Invariant checks:** generated finite states and inputs validate the derivative identities; smooth trajectories validate integrated momentum/energy, including negative electrical work and nonzero external work. Deliberately perturb a reaction-torque sign in a test-local mutant and verify that the identity detects it.
3. **Numerics:** the full coupled plant under smooth fixed inputs has independent DOP853/matrix-exponential checks and an error-versus-step table. Default-resolution scaled physical-state discrepancy should be below `1e-6`; inspect the observed convergence rather than silently loosening thresholds. Time and tolerances are reported.
4. **Controller cases:** nominal rest-to-target; finite torque pulse; preloaded wheel (`omega_w0=120 rad/s`); sustained external torque demonstrating finite momentum capacity; zero-terminal-voltage driver failure; stuck-positive-voltage fault; increased bearing drag. Both controllers run the same cases and inputs. A fault that leaves the nominal state unaffected must be paired with a later disturbance or demand so the test is meaningful.
5. **Monte Carlo:** 64 fixed, fully recorded independent uniform draws using NumPy PCG64 and seed 20261023. Ranges: `J_b=[0.035,0.065]`, `J_w=[0.0007,0.0013]`, `R=[1.5,2.5]`, `L=[0.008,0.012]`, `k=[0.04,0.06]`, `b=[0.000005,0.000015]`; initial body angle ±0.1 rad, body rate ±0.01 rad/s, absolute wheel rate ±100 rad/s, current zero; target ±0.5 rad, torque pulse ±0.005 N m from 6–7 s, horizon 20 s. Use the same draws for both controllers and the fixed default nominal model/gains for control. Keep `k_e=k_t` per draw. Publish every input and outcome, including trips/aborts, not only successful runs. This estimates sensitivity within the synthetic distribution, not hardware reliability.
6. **Metrics:** terminal-window angle/rate errors, settling time, current/relative-speed peaks, gate occupancy, hard trips, abort status, supplied/regenerated work, losses and invariant residuals. Tracking success requires final two-second angle error ≤0.01 rad and body-rate magnitude ≤0.002 rad/s, no hard trip/abort and no observed hard-limit excursion. No requirement that the proposed controller win every case.

Closed-loop reference tests use an independently coded controller and reduced-coordinate SciPy plant at the same sample times. Separately replay the C++ applied-voltage schedule through the reference to isolate plant integration from policy differences. Agreement near a trip boundary is reported at controller-tick resolution, rather than forcing coincident continuous event times.

## Product, storage and report

Produce one bounded CLI executable plus `make verify` for a complete replay. CLI simulation presets permit documented numeric overrides; exact inputs accompany every output. Write traces as CSV and summaries as JSON with scenario/controller version, toolchain versions and source hashes. Generate standard Matplotlib PNG/PDF plots of dynamics/current, work balance, convergence and paired Monte Carlo outcomes, plus a standalone HTML report with units, captions, methods, failures and source links. No network assets are needed to read the report.

Standalone setup and reproduction commands are in [README](../README.md). The build cache defaults to `~/.cache/actuator-lab`. The existing guard limits that cache to 200 MiB and requires more than 2 GiB host free space; the separate Python virtual environment is outside that cache. Retained historical evidence is under 20 MiB. Plotting dependencies are installed in a scoped target after wheel metadata/size inspection.

Input/config caps: finite numeric fields; horizon at most 120 s; controller interval 0.001–0.05 s; 1–1000 substeps; at most 250,000 controller samples and 5,000,000 integration steps per invocation; output at controller ticks plus bounded event records. Plant ranges: `J_b=[0.001,10]`, `J_w=[0.000001,1]`, `R=[0.1,100]`, `L=[0.00001,1]`, `k=[0.0001,1]`, `b=[0,0.1]` in the declared SI units. Scheduled external torque is bounded by ±0.05 N m and bearing multipliers by [1,100]. Positive plant values and the largest scheduled effective bearing friction must also satisfy the solver time-scale gate. Initial/target angles are bounded by ±pi; initial body rate by ±5 rad/s; initial current and relative speed must lie inside their hard limits. Default protection limits are fixed for the comparative experiments, not tuned per case. Numerical abort envelope: `|theta_b|>100 rad`, `|omega_b|>100 rad/s`, `|omega_w|>2000 rad/s` or `|i|>50 A`; these are explicit supported-model limits, not physical protections.

Retain full traces for the named cases and at most four representative Monte Carlo trials. Keep every Monte Carlo input, outcome and event summary; transient per-trial traces may be discarded after metrics are computed and can be regenerated from the recorded inputs. This keeps retained artifacts below the 20 MiB cap without hiding failed trials.


A separate AI reviewer inspected the final physics, source and historical results. [Review evidence](independent-employer-review.md) distinguishes source checks, executed experiments, synthetic uncertainty and unverified hardware/personal qualifications.
