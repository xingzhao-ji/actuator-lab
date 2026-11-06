# Coordinates, power balance and numerical oracles

This is a synthetic educational model, not an identified motor or qualified spacecraft model. It exercises a narrow numerical ODE and electromechanical example and does not establish general EM expertise or personal mastery.

## Physical convention and dimensions

The body and wheel rotate about one common inertial axis. The wheel's absolute spin inertia is `Jw`; `Jb` excludes that wheel spin inertia. `omega_b` and `omega_w` are absolute angular rates; `r = omega_w - omega_b` is motor rotor speed relative to the stator/body. Body angle is unwrapped, with no modulo operation. No gravity potential or off-axis rotational dynamics is modeled.

| Quantity | Unit | Synthetic default |
|---|---|---|
| Body / wheel inertia `Jb`, `Jw` | kg m² | 0.05 / 0.001 |
| Resistance `R` | ohm | 2 |
| Inductance `L` | H | 0.01 |
| Torque / back-EMF constant `k` | N m/A = V s/rad in consistent SI | 0.05 |
| Bearing coefficient `b` | N m s/rad | 0.00001 |
| Terminal voltage `V` | V | commanded within ±12 |
| External body torque `tau_ext` | N m | scenario dependent |

A positive current exerts `k*i` on the wheel and the opposite torque on the body. Relative bearing friction opposes relative motion. With `b_eff = b * scheduled_multiplier`:

```text
tau = k*i - b_eff*r
theta_b' = omega_b
omega_w' = tau/Jw
omega_b' = (tau_ext - tau)/Jb
i' = (V - R*i - k*r)/L
```

Using a single SI `k` explicitly enforces the torque/back-EMF conversion pair. The [University of Michigan CTMS motor/Simscape tutorial](https://ctms.engin.umich.edu/CTMS/?example=MotorPosition&section=SimulinkSimscape) supports equality in SI. [Maxon's simulation guidance](https://support.maxongroup.com/hc/en-us/articles/360013761160-Motor-data-and-simulation) discusses electrical constants, unit conversions and inductance. Neither source validates these synthetic default values.

## Angular momentum and work

Adding the two mechanical equations gives `H' = tau_ext` for `H = Jb*omega_b + Jw*omega_w`. Internal motor and bearing torques cannot change total angular momentum.

Let `E = (Jb*omega_b² + Jw*omega_w² + L*i²)/2`. Multiplying the mechanical equations by their respective angular rates and the circuit equation by current gives:

```text
E' = omega_b*tau_ext + (omega_w-omega_b)*(k*i-b_eff*r)
     + i*(V-R*i-k*r)
   = V*i - R*i² - b_eff*r² + tau_ext*omega_b
```

The external body-work term is essential. Electrical terminal work may be negative under regeneration. Copper and bearing loss are nonnegative. Five quadratures are integrated in the same RK4 stages as the four physical states:

```text
W_e' = V*i             Q_R' = R*i²       Q_b' = b_eff*r²
W_ext' = tau_ext*omega_b                 I_ext' = tau_ext
energy defect = E-E0-W_e+Q_R+Q_b-W_ext    [J]
momentum defect = H-H0-I_ext              [N m s]
```

Zero terminal voltage leaves a closed electrical circuit; the inductor current evolves continuously and may regenerate/brake. It is not an open-circuit fault. No safety action resets current, wheel speed, momentum or energy. A stuck voltage fault overrides the commanded inhibit.

## Independent coordinates and references

The Python reference evolves `[theta_b,H,r,i]`, not the C++ absolute rates. Define `Jsum = Jb+Jw`, `Jeff = Jb*Jw/Jsum`:

```text
H' = tau_ext
r' = (k*i-b_eff*r)/Jeff - tau_ext/Jb
i' = (V-R*i-k*r)/L
theta_b' = (H-Jw*r)/Jsum
omega_b = (H-Jw*r)/Jsum; omega_w = omega_b+r
```

SciPy DOP853 integrates these equations and independently formed quadratures on each held-input interval (`rtol=1e-11`, `atol=1e-12`). For smooth constant forcing, an affine 5×5 matrix in `[theta,H,r,i,1]` yields a second reference through `scipy.linalg.expm`. A tighter DOP853 run checks reference sensitivity. [SciPy documents DOP853 and tolerance semantics](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html); the actual runtime version is retained in results.json.

Independent analytic limits used by the tests:

- At `k=b=0`, `i(t)=V/R+(i0-V/R)*exp(-Rt/L)`.
- At `k=0,V=tau_ext=0`, relative speed is `r0*exp(-b*t/Jeff)` and total momentum is constant; body angle follows the integral of `(H-Jw*r)/Jsum`.
- With `k=b=0`, constant external torque gives `omega_b=omega_b0+tau_ext*t/Jb`, `theta=theta0+omega_b0*t+tau_ext*t²/(2Jb)` and exact impulse/body-work changes.

The core permits `k=0` only for internal analytic tests. Production config admission requires positive `k`.

## Sampling, safety and solver admission

Default controller sampling is 0.01 s with 20 RK4 substeps. Every scheduled event occurs on an integer sample tick. All stages of the preceding RK4 step use its left-held input, including the final stage at the right endpoint. There is no accidental one-stage anticipation of a fault.

Voltage is saturated at ±12 V. The cascaded current request is saturated at ±2 A. Sampled |i| ≥ 2.5 A or |r| ≥ 200 rad/s latches zero commanded terminal voltage. The soft 150 rad/s gate suppresses requested internal torque that would accelerate outward, but it cannot guarantee a speed invariant: residual current, external torque, sample delay and a stuck driver remain physical. Maxima and excursions are observed at RK4 substep endpoints, not proven over continuous time.

An admitted step obeys `h <= 0.25*min(L/R, sqrt(L*Jeff)/k, Jeff/b_eff)` with the last term omitted for zero drag. The maximum scheduled drag participates in admission. This conservative heuristic is not a control stability theorem. All input bounds and numerical abort envelopes are in design.md and enforced by the CLI; out-of-envelope integration retains the last admissible state with explicit failure status. No state is clipped to fake safety.

Smooth convergence was frozen at `t=0.025 s`, `V=1 V`, `tau_ext=0.003 N m`, zero initial state, with steps 0.001/0.0005/0.00025 s before observing errors. It measures fourth-order state and work-balance convergence during the transient, away from long-time roundoff. No fourth-order convergence claim is made across hybrid trip/saturation events.

## Why the baseline can fail

The direct baseline is a transparent voltage PD controller with the same outer torque gains as the cascade. It lacks back-EMF compensation and is not an optimal conventional controller. At zero external torque, constant relative speed and zero body rate require `i=b*r/k` and `V=(R*b/k+k)*r`. Direct voltage `V=(R/k)*Kp*error` therefore requires the steady error

```text
error = (b + k²/R)*r/Kp
```

under nominal parameters. A 0.01 N m s impulse leaves `r=10 rad/s` at zero body rate in this nominal wheel, predicting 0.105 rad offset, as seen in the pulse result. An initially biased wheel similarly exposes the missing compensation and may also cause a startup current trip. Consequently 0/64 direct versus 64/64 cascade does not by itself establish novel controller superiority or reliability.

The follow-up feedforward ablation retains the cascade's nominal back-EMF/bearing compensation, current-demand clamp, outer gains and supervisor, while setting current feedback `Kc=KI=0`. It uses the same frozen trials without retuning/resampling and is explicitly post-observation, not part of the originally frozen two-controller experiment. The original results and exact source hashes are preserved under evidence/checkpoints/original-paired.

[NASA's momentum-management explanation](https://science.nasa.gov/learn/basics-of-space-flight/chapter11-2/) and [NASA's GNC survey](https://www.nasa.gov/smallsat-institute/sst-soa/guidance-navigation-and-control/) describe the underlying momentum exchange/saturation constraint. This experiment has no external desaturation actuator, so no controller can indefinitely reject a persistent torque while keeping bounded wheel momentum and fixed body attitude.
