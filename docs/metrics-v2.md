# Observational metrics contract (schema version 1)

This additive measurement extension completes the original requested settling,
command-gate occupancy and gross terminal-energy metrics. Original evidence,
experiment dates, outcomes and acceptance documents remain historical evidence.
The extension's 213-run replay, parity and numerical checks are a separate later
acceptance step; this document makes no new measured result-count claim.

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
