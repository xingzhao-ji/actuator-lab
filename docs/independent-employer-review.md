# Independent AI-assisted physics and evidence review

Historical review dated 2026-10-23 by a fresh AI reviewer agent, separate from the builder. This is artifact review, not employer endorsement. Public packaging removed private hiring/portfolio commentary and redacted command paths; numerical findings are preserved. **Accepted within the documented synthetic, one-axis simulation scope. No blocking correctness or evidence defect was found.** This judgment concerns the artifact; it does not certify the user's personal expertise, physical equipment or production control software.

The review covered README, design, derivation, implementation plan, progress and design-review records; every C++ production source/header and test; Python references, experiment generation, aggregation and report code; CLI/resource/manifest contracts; frozen inputs, all outcome summaries, original source/results checkpoint and all five exported figures. No production source or original evidence was changed by the reviewer. Review code, logs and results are retained under `evidence/independent-review*`.

## Independently executed verification

Fresh compilation and tests used a separate local cache subtree, with the existing Python environment unchanged:

Historical command: `make test sanitize` with a separate review cache and the original Python 3.12 environment, followed by the retained [review probe source](../evidence/independent-review-probe.py). See the [evidence provenance note](../evidence/README.md) before using this historical probe.

The first command exited 0: 27 C++ tests, 32 Python tests, and the core/simulation AddressSanitizer plus UndefinedBehaviorSanitizer binaries passed. The existing tests are builder-authored checks; their rerun is distinguished from the independent probes below.

The reviewer wrote an additional oracle without importing project plant, controller or reference code. It constructs the affine dynamics in **absolute body/wheel coordinates**, then propagates the 25 second moments of `[theta, omega_b, omega_w, current, 1]` with a Kronecker-sum matrix. Five appended power/impulse integrals obtain state and work results through a matrix exponential. This checks work independently of both the C++ RK stages and the existing reduced-coordinate DOP853 implementation. The oracle still shares SciPy's matrix-exponential library with one project reference; it is not an independent linear-algebra library.

| Executed check | Observed result |
|---|---|
| Baseline manifest and original archive | All 71 recorded files and all 18 original archived source members matched SHA-256; archive membership exactly covered the original source ledger |
| Fresh-binary replay | All 21 named and 192 Monte Carlo runs matched recorded raw summary and CSV hashes: 213/213 |
| Original versus follow-up | Every direct/cascaded named and MC summary/trace hash still matched the preserved original; identical frozen input hash |
| New signed/biased constant-forcing fixtures | 32 new cases at two resolutions, including zero bearing drag, nonzero initial current, both voltage signs and both external-torque signs, passed the independent oracle |
| Default-step oracle discrepancies | Maximum scaled physical-state error `2.2125e-7`; maximum work error `4.1369e-7 J` |
| Four-times-finer oracle discrepancies | Maximum scaled physical-state error `8.1956e-10`; maximum work error `1.5480e-9 J`; every new fixture's state/work error improved by more than 100× |
| Both sides of scheduled discontinuities | 48 intervals passed independent held-input propagation; maximum scaled state error `1.4662e-6`, work error `5.6314e-7 J` |
| MC integration refinement | All 192 success/trip/abort/excursion flag sets unchanged at `h=0.000125 s`; largest terminal-angle metric change `1.5302e-10 rad`, rate change `2.7512e-13 rad/s` |
| Plots/report | All five PNGs visually inspected; quantities, units, threshold legends and failure cases are legible; HTML source embeds the figures and discloses limits |

The state-error scales are the project's explicit `1 rad`, `1 rad/s`, `100 rad/s`, and `1 A`. Error improvement in these new smooth fixtures is additional numerical evidence, not a claim about every allowed parameter or hybrid controller transition. Reviewer probe execution took approximately 10.25 seconds; the scoped cache guard afterwards reported 75,124,736 allocated bytes and 152,586,510,336 host free bytes.

Full evidence: [fresh test log](../evidence/independent-review-tests.txt), [probe source](../evidence/independent-review-probe.py), [probe log](../evidence/independent-review-probes.txt), [all independent results/configs](../evidence/independent-review-results.json). The reviewed numerical results SHA-256 is `d69e150d0b2706265f118a8ef56f327c9ef2b45a5404b0f89fd05dea972c4e89`. The original manifest hash in the probe results identifies the pre-review artifact set; later manifests can legitimately include these new review files.

## Physics and control assessment

The model's signs and units are consistent. Positive motor current accelerates the wheel and reacts against the body. Both back EMF and bearing torque depend on wheel speed relative to the body. The SI motor constant makes mechanical conversion power `k*i*(omega_w-omega_b)` cancel its electrical counterpart. Total angular momentum changes only by external body torque. Stored energy changes by terminal electrical power minus copper and bearing loss plus external body mechanical work. The latter term is present in equations, RK stages, independent references and diagnostics.

All nine states share the RK4 stages. Integer event ticks with left-held inputs prevent a final RK stage from anticipating a disturbance or driver fault. Zero voltage correctly means closed terminals, with continuous current and mechanical states. The stuck driver is applied after the commanded inhibit and can defeat it. The code does not clip physical states to manufacture energy, momentum or safety. Numerical-envelope aborts are explicit failures with the last admissible state retained.

The voltage rail, current-demand clamp, sampled trip and speed command gate have distinct semantics. A 2 A command bound is not a measured current invariant. The 150 rad/s soft gate is not guaranteed momentum unloading or a continuous speed bound. Observed maxima include RK substep endpoints; they are not continuous-time extrema. The report correctly retains cascade failures for sustained torque, voltage loss, stuck drive and increased drag. In particular, cascade sustained-torque failure occurs without a measured hard-limit trip: bounded relative wheel speed does not imply successful attitude control.

The 0/64 direct versus 64/64 cascaded outcome is real for the frozen experiment, but the direct comparator predictably lacks the back-EMF term required at nonzero wheel momentum. Its nominal pulse offset of about `0.105 rad` follows the stated equilibrium algebra. The feedforward comparison materially improves the interpretation: it preserves nominal compensation, command clamp and supervisor while removing current feedback, and passes 10/64. This remains a post-observation ablation with fixed gains, not a preregistered optimal-controller comparison or a new control-theory result.

The deterministic input generator, rejection-on-input-change, complete trial denominator, failure retention and exact repeated outputs support reproducibility. The reconstructed original archive matches its previously recorded source hashes, as explicitly disclosed. Local hashes prove byte consistency; they do not independently establish when a study was frozen or provide an external preregistration timestamp. Nothing in this review upgrades the synthetic sweep into field reliability, statistical generalization, manufacturer calibration or hardware validation.

## Nonblocking limitations and follow-up priorities

1. **Narrower metrics than the design proposed.** Design item 6 lists settling time, gate occupancy and supplied/regenerated work. Current structured results emphasize terminal-window maxima, limits and balance defects; named traces expose gate flags and signed cumulative electrical work. They do not provide a complete per-trial summary of those additional proposed metrics. Net electrical work is not separate gross supplied and regenerated energy. Do not describe those extra metrics as already delivered. The acceptance criteria and reported controller counts do not depend on them.
2. **Compact implementation, limited engineering surface.** The core is intentionally small and often compresses several operations into one line. This is sufficient to inspect the model, but conventional formatting and explicit named limit/gain constants would improve maintenance. It does not supply substantial new evidence of concurrency, production latency, distributed operation, hardware drivers or API compatibility.
3. **Limited plant and controller scope.** This is a linear one-axis motor/body model with ideal measurements and fixed nominal controllers. There is no identified physical parameter set, switching drive, temperature model, sensor estimator, off-axis rigid-body dynamics, desaturation actuator, real-time scheduler or closed-loop stability proof. The solver admission rule is appropriately described as a heuristic. Verification samples and analytic limits cannot prove all admitted configurations accurate or safe.
4. **Follow-up comparisons would require new labels.** Additional gain tuning, noise/delay studies or a holdout uncertainty distribution could be useful, but would be new experiments. They should not replace or silently reinterpret this frozen result. No extra implementation is required to accept the current bounded claim.
