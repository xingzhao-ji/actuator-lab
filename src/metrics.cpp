#include "actuator/metrics.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace actuator {
MetricAccumulator::MetricAccumulator(double step_s,std::int64_t planned_steps,double target,const State& initial)
    :step_s_(step_s),target_(target),planned_steps_(planned_steps),required_tail_steps_(0) {
    if(!std::isfinite(step_s)||step_s<=0||planned_steps<0||!std::isfinite(target))
        throw std::invalid_argument("invalid metric observation grid");
    double dwell_steps=2.0/step_s;
    const double rounded=std::round(dwell_steps);
    // Valid production grids divide one second. Correct representation error
    // before ceil, then use integer endpoint differences for all dwell tests.
    if(std::abs(dwell_steps-rounded)<=8*std::numeric_limits<double>::epsilon()*std::max(1.0,dwell_steps))
        dwell_steps=rounded;
    if(!std::isfinite(dwell_steps)||dwell_steps>=static_cast<double>(std::numeric_limits<std::int64_t>::max()))
        throw std::invalid_argument("metric observation grid is too fine");
    required_tail_steps_=static_cast<std::int64_t>(std::ceil(dwell_steps));
    observe_tracking(initial);
}
void MetricAccumulator::observe_tracking(const State& state) {
    if(std::abs(state[theta]-target_)<=.01&&std::abs(state[body])<=.002) {
        if(!tail_start_step_)tail_start_step_=completed_steps_;
    }else {
        last_violating_step_=completed_steps_;
        tail_start_step_.reset();
    }
}
void MetricAccumulator::accept(const State& endpoint,const ControlResult& held,double voltage,const RKStages& stages) {
    ++completed_steps_;
    observe_tracking(endpoint);
    const std::array<bool,4> flags{held.speed_gate,held.current_clamp,held.voltage_clamp,held.trip};
    for(unsigned j=0;j<4;++j)if(flags[j])++gate_steps_[j];
    const auto& i=stages.currents;
    const auto positive=[&](unsigned j){return std::max(voltage*i[j],0.0);};
    const auto negative=[&](unsigned j){return std::max(-voltage*i[j],0.0);};
    supplied_+=step_s_/6*(positive(0)+2*positive(1)+2*positive(2)+positive(3));
    regenerated_+=step_s_/6*(negative(0)+2*negative(1)+2*negative(2)+negative(3));
}
ObservationalMetrics MetricAccumulator::finish(bool aborted,double net_work) const {
    ObservationalMetrics result;
    result.observation_step_s=step_s_;
    result.completed_steps=completed_steps_;
    result.observed_duration_s=completed_steps_*step_s_;
    result.planned_duration_s=planned_steps_*step_s_;
    result.last_violating_step=last_violating_step_;
    result.qualifying_tail_start_step=tail_start_step_;
    if(aborted||completed_steps_!=planned_steps_)result.tracking_settling_status="incomplete";
    else if(planned_steps_<required_tail_steps_)result.tracking_settling_status="insufficient_horizon";
    else if(tail_start_step_&&completed_steps_-*tail_start_step_>=required_tail_steps_) {
        result.tracking_settling_status="settled";
        result.tracking_settling_time_s=*tail_start_step_*step_s_;
    }else result.tracking_settling_status="not_settled";
    for(unsigned j=0;j<4;++j) {
        result.gate_durations_s[j]=gate_steps_[j]*step_s_;
        if(completed_steps_>0)result.gate_fractions[j]=result.gate_durations_s[j]/result.observed_duration_s;
    }
    result.supplied_energy_J=supplied_;
    result.regenerated_energy_J=regenerated_;
    result.net_electrical_work_J=net_work;
    result.energy_split_residual_J=supplied_-regenerated_-net_work;
    return result;
}
}
