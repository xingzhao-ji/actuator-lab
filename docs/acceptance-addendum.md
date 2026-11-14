# Scope and design deviations

Integration update, 2026-10-23. Actuator Lab is a bounded synthetic, one-axis numerical/control artifact. This public package makes documented setup/text transformations; [publication provenance](publication-provenance.json) distinguishes those changes from the unchanged numerical source and historical outcomes.

The experiment record contains 121 gates. See the [original manifest](../evidence/manifest.json).

On the same frozen 64 synthetic inputs, direct voltage control succeeds in 0/64, feedforward in 10/64 and cascaded current feedback in 64/64. The feedforward ablation was added after observing the direct/cascade results, with no resampling or retuning of those inputs. It is a labeled follow-up, not preregistration or proof of an optimal controller. Failures under sustained torque, voltage loss, stuck drive and increased drag remain in the record. Neither these counts nor the soft speed gate establishes population reliability, a continuous-time safety guarantee or physical hardware performance.

**Design deviation:** proposed settling-time, gate-occupancy and separate gross supplied/regenerated energy summaries were not delivered. Current structured outputs instead provide terminal-window maxima, limit/abort outcomes and balance defects; traces provide gate flags and signed cumulative electrical work. Net electrical work is not separate supplied and regenerated energy. The implemented acceptance gates do not depend on those extra metrics. The November 2026 [additive measurements](metrics-v2.md) complete them separately.

This scope excludes reinforcement learning, orbital mechanics, general electromagnetics, three-dimensional spacecraft dynamics, calibrated physical parameters, hardware drivers, physical actuator tests and flight qualification.
