#pragma once
#include "control.hpp"
#include <string>
#include <vector>
namespace actuator {
struct RunConfig {
    Params plant{},nominal{};State initial{};
    std::string scenario="nominal";ControllerKind controller=ControllerKind::cascaded;
    double target=0.5235987755982988,Tc=.01,pulse=.01,fixed_voltage=1,external=.003,fault_voltage=12,drag_multiplier=30;
    int ticks=2000,substeps=20;
};
struct Sample {double time;State state;Input input;ControlResult control;};
struct RunResult {
    std::vector<Sample> samples;std::vector<std::string> events;
    bool aborted=false,tripped=false,success=false,excursion=false;
    std::string reason="completed";
    double max_current=0,max_relative_speed=0,max_energy_defect=0,max_momentum_defect=0,terminal_angle_error=0,terminal_body_speed=0;
    int completed_steps=0;
};
void validate(const RunConfig&);
Input schedule(const RunConfig&,int tick,double command);
RunResult simulate(const RunConfig&);
}
