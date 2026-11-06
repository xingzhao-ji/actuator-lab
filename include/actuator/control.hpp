#pragma once
#include "model.hpp"
namespace actuator {
enum class ControllerKind {direct,cascaded,feedforward};
struct ControlMemory {double integral=0;bool tripped=false;};
struct ControlResult {
    double requested_voltage=0,commanded_voltage=0,current_reference=0;
    bool speed_gate=false,current_clamp=false,voltage_clamp=false,trip=false;
};
ControlResult control(const State&,const Params&,ControllerKind,ControlMemory&,double target,double Tc);
}
