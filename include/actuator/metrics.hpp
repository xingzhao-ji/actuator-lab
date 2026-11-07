#pragma once
#include "control.hpp"
#include <array>
#include <cstdint>
#include <optional>
#include <string>

namespace actuator {
// Gate array order is also the serialized object key order.
inline constexpr std::array<const char*,4> metric_gate_names{
    "speed_gate","current_clamp","voltage_clamp","trip"};
struct ObservationalMetrics {
    int schema_version=1;
    std::string tracking_settling_status="incomplete";
    std::optional<double> tracking_settling_time_s;
    double observation_step_s=0;
    std::int64_t completed_steps=0;
    double observed_duration_s=0,planned_duration_s=0;
    double supplied_energy_J=0,regenerated_energy_J=0;
    double net_electrical_work_J=0,energy_split_residual_J=0;
    std::array<double,4> gate_durations_s{};
    std::array<std::optional<double>,4> gate_fractions{};
    std::optional<std::int64_t> last_violating_step,qualifying_tail_start_step;
};
class MetricAccumulator {
public:
    MetricAccumulator(double step_s,std::int64_t planned_steps,double target,const State& initial);
    // Call only after the candidate physical state has passed admission.
    void accept(const State& endpoint,const ControlResult& held,double actual_voltage,const RKStages&);
    ObservationalMetrics finish(bool aborted,double net_electrical_work_J) const;
private:
    void observe_tracking(const State&);
    double step_s_,target_;
    std::int64_t planned_steps_,completed_steps_=0,required_tail_steps_;
    std::optional<std::int64_t> last_violating_step_,tail_start_step_;
    std::array<std::int64_t,4> gate_steps_{};
    double supplied_=0,regenerated_=0;
};
}
