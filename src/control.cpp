#include "actuator/control.hpp"
#include <algorithm>
#include <cmath>
namespace actuator {
ControlResult control(const State& x,const Params& nominal,ControllerKind kind,ControlMemory& memory,double target,double Tc) {
    ControlResult out;const double r=x[wheel]-x[body];
    memory.tripped=memory.tripped||std::abs(x[current])>=2.5||std::abs(r)>=200;
    out.trip=memory.tripped;
    if(out.trip)return out;
    double torque=.12*(x[theta]-target)+.16*x[body];
    if(std::abs(r)>=150&&torque*r>0){torque=0;out.speed_gate=true;}
    if(kind==ControllerKind::direct)out.requested_voltage=nominal.R/nominal.k*torque;
    else {
        const double raw_current=(torque+nominal.b*r)/nominal.k;
        out.current_reference=std::clamp(raw_current,-2.,2.);
        out.current_clamp=raw_current!=out.current_reference;
        const double error=out.current_reference-x[current];
        out.requested_voltage=nominal.R*out.current_reference+nominal.k*r;
        if(kind==ControllerKind::cascaded) {
            out.requested_voltage=nominal.R*out.current_reference+nominal.k*r+.5*error+5*memory.integral;
            if(std::abs(out.requested_voltage)<=12||(out.requested_voltage>12&&error<0)||(out.requested_voltage< -12&&error>0))memory.integral+=Tc*error;
        }
    }
    out.commanded_voltage=std::clamp(out.requested_voltage,-12.,12.);
    out.voltage_clamp=out.requested_voltage!=out.commanded_voltage;
    return out;
}
}
