# Observational metrics contract (schema version 1)

This additive measurement extension completes the original requested settling,
command-gate occupancy and gross terminal-energy metrics. Original evidence,
experiment dates, outcomes and acceptance documents remain historical evidence.
The extension's 213-run replay, parity and numerical checks are separately dated
measurements reported below. Independent review and publication are separate
acceptance steps.

Each CLI `summary.json` gains `observational_metrics`. Existing summary fields and
CSV columns retain their meaning. The nine physical/work/impulse states, control
equations, input schedules and physical RK4 arithmetic are unchanged. The new
accumulators never feed the plant or controller.

Tracking uses inclusive absolute angle-error <= 0.01 rad and body-rate <= 0.002
rad/s thresholds. It observes step 0 (the initial state) and every accepted
integration endpoint. `qualifying_tail_start_step` is the first in-band point
after the last violation, or zero if no point violated; it is null when the last
point is out of band. `last_violating_step` is null if no observed point violated.
These audit indices refer to integration steps, not controller rows. A candidate
qualifies only if the final uninterrupted in-band tail spans at least 2 seconds.
No continuous-time guarantee follows from the observed endpoints.

`tracking_settling_time_s` is the qualifying index times `observation_step_s`,
with `tracking_settling_status: settled`. It is null for `not_settled` (complete
horizon >=2 s, tail too short), `insufficient_horizon` (complete horizon <2 s),
or `incomplete` (aborted, regardless of the apparent observed prefix). An
initially in-band run may settle at zero. This tracking metric is separate from
legacy `success`; trip or limit failure does not prevent tracking from settling.
Dwell is compared using integer step counts, correcting only representational
roundoff near an integer 2-second step count.

`gate_durations_s` and `gate_fractions` have independent `speed_gate`,
`current_clamp`, `voltage_clamp` and `trip` keys. Each left-held control decision
counts for each accepted step under that decision. Durations are step counts
times `observation_step_s`; fractions divide by `observed_duration_s`, and are
null when that denominator is zero. Overlapping flags need not sum to one. The
final controller row has no following interval and contributes zero duration.
An aborted partial interval contributes only its accepted prefix.

`supplied_energy_J` and `regenerated_energy_J` separately integrate positive and
negative terminal power magnitudes using actual fault-adjusted held voltage and
RK4 stage currents, with weights (1,2,2,1)*h/6. A rejected candidate adds neither
energy nor occupancy nor endpoint observations. `net_electrical_work_J` records
the existing signed electrical-work state; `energy_split_residual_J` is supplied
minus regenerated minus net electrical work. Gross values are nonnegative.
Sign changes within a step can contribute to both gross values even when net
work cancels. Positive/negative-part integrands are nonsmooth at crossings, so
the original smooth fourth-order integration claim does not apply to the split
quadratures. These are synthetic numerical terminal-energy estimates, not
battery recovery efficiency, hardware measurements or validated battery models.

`completed_steps` and `observed_duration_s` describe accepted integration only;
`planned_duration_s` describes the declared full horizon. Resolution is
`observation_step_s` in seconds; energy is in joules, times/durations in seconds,
and fractions are dimensionless. The nested `schema_version` is 1. JSON has no
NaN or Infinity. Status and null values preserve failed/short/empty-prefix runs
without fabricating successful completion or shrinking a denominator.

Native and CLI boundary verification is available via `make test` (with the
repository's normal guard), or direct commands inside an admitted outer guard.
Private resource supervisors and receipts are deliberately outside the public
source contract. The separate measurement extension must pass fixed-cohort exact
legacy parity, independent gross-energy reference and resolution sensitivity
before measured claims are added to the README.

## Additive replay and offline recovery

`python/measurements.py plan --output CACHE/fixed-plan.json` reads the exact
historical frozen-input/result identities and freezes the complete original
ordered list: 21 named and 192 Monte Carlo slots. No defaults are resampled.
`replay --plan ... --binary ... --output CACHE/replay --request ...` executes
that list serially. The request is the externally retained execution provenance;
production replay requires clean committed source and the accepted binary hash.
Use an admitted outer supervisor with `ACTUATOR_CACHE` set. Do not nest guards.
The `metrics-plan`, `metrics-replay` and `metrics-finalize` Makefile targets expose
these commands; override `GUARD=` only inside an already admitted outer guard.

Every completed slot is flushed and fsynced to `events.jsonl` after strict legacy
summary/trace parity and metric checks, before its disposable raw trace is
removed. A failed slot retains its raw files and halts without retry. The
finalizer reconstructs all fixed slots, including missing/error/invalid statuses;
it preserves a malformed or unterminated final record explicitly. It never runs
the simulator. Sensitivity has its own 33-slot plan and ledger. Reference replay
has a nine-slot plan and a separate `--finalize-plan ... --ledger ... --output ...`
recovery mode. Never overwrite an earlier output or ledger when recovering.

`python/metric_reference.py` uses independent absolute body/wheel coordinates,
DOP853 and split terminal-power integrals at rtol 1e-11/atol 1e-12. The historical
retained CSV inputs are used only after their decompressed hashes match the new
fixed replay. Original accepted-substep endpoints determine independent tracking
checks. `measurements.py sensitivity` uses all named slots and MC IDs 0,21,42,63
for all three controllers with exactly four times the original substeps.
Both phases retain every energy/status/time comparison; failures halt for review.
`python/metric_report.py` consumes those artifacts without simulation and emits
standalone offline HTML, a 213-row CSV, and PNG/PDF scientific figures.

Commands displayed in public run records are explicitly normalized for
portability. The immutable exact raw command remains private, linked by SHA256;
absolute local paths and private supervisors are excluded from public metadata.
The original accepted experiment was October 2026. Extension execution timestamps
and later publication verification are separate and do not renew old experiments.
The historical Task1 compiler identity was observed only after its builds; pinned
binary reuse and prospective compiler gates do not establish earlier provenance.

## Measured extension — November 7, 2026 UTC

The [offline report](../evidence/metrics-v2/report.html) records a complete
213/213 fixed replay: all 21 named and 192 Monte Carlo configurations retain exact
legacy CSV hashes and parsed legacy summaries, including event lists. No slots
are missing, invalid, or retried. All energy identities pass; the largest absolute
split residual is **1.0658141036401503e-13 J**. This new replay is separate from
the original October 2026 experiment and later publication checks.

| Cohort | Controller | Tracking settled | Not settled | Original success |
|---|---|---:|---:|---:|
| Named | direct | 1/7 | 6/7 | 1/7 |
| Named | cascaded | 3/7 | 4/7 | 3/7 |
| Named | feedforward | 3/7 | 4/7 | 3/7 |
| Frozen MC | direct | 0/64 | 64/64 | 0/64 |
| Frozen MC | cascaded | 64/64 | 0/64 | 64/64 |
| Frozen MC | feedforward | 10/64 | 54/64 | 10/64 |

Every run completed its declared horizon; none is `incomplete` or
`insufficient_horizon`. Settling and original success remain separate definitions
although their counts coincide here. All three stuck-positive named runs retain
their unsuccessful, excursion-positive outcomes.

All nine independent reference comparisons passed: nominal, bias and
stuck-positive for each controller. Maximum gross-energy absolute error was
**5.8558212723269776e-08 J**; settled times matched at the original endpoints.
All 33 sensitivity comparisons passed: 21 named plus MC IDs 0,21,42,63 for each
controller, at four times the original substeps. Maximum gross-energy difference
was **0.00018475959543673426 J**, within the prescribed absolute-plus-relative
limit; maximum settled-time difference was **0.000375 s**, below one original
0.01 s controller interval. All settling statuses, legacy success/abort/trip/
excursion flags and event lists agreed. All gate-duration differences were zero.
Individual comparisons and their limits are retained, including larger-energy
cases where the allowed absolute difference is correspondingly larger.

The gate figure displays medians, which can be zero despite interventions.
Named direct/cascaded/feedforward runs with any speed gating number **1/1/1**
(out of seven each); any current clamp **0/2/2**; any voltage clamp **1/2/0**;
any trip-latched duration **4/1/1**. Among the 64 MC inputs, direct has nine runs
with trip-latched duration, while cascaded and feedforward have none. Other MC
gate durations are all zero. The [213-row CSV](../evidence/metrics-v2/runs.csv)
retains each fraction, and the full JSON retains durations and denominators.

The [resource summary](../evidence/metrics-v2/resource-summary.json) links all
private raw receipts and immutable requests by SHA256, including expected RED
and initial fixture failures. No numerical/parity/guard failure occurred in the
four admitted measurement/report phases. Sampling bounds refer to resource-probe
start timestamps; they do not establish continuous observation or a
completion-to-completion cadence. The original provenance and scope limitations
above continue to apply.
