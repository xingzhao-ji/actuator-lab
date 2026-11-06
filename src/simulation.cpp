#include "actuator/simulation.hpp"
#include <stdexcept>
#include <algorithm>
#include <cmath>
#include <set>
namespace actuator {
void validate(const RunConfig& c) {
    auto bound=[](double v,double lo,double hi){if(!std::isfinite(v)||v<lo||v>hi)throw std::invalid_argument("run value outside finite admitted bounds");};
    bound(c.Tc,.001,.05);bound(c.target,-3.141592653589793,3.141592653589793);
    bound(c.pulse,-.05,.05);bound(c.external,-.05,.05);bound(c.fixed_voltage,-12,12);bound(c.fault_voltage,0,12);bound(c.drag_multiplier,1,100);
    if(std::abs(1/c.Tc-std::round(1/c.Tc))>1e-9)throw std::invalid_argument("sample interval must divide one second for exact event ticks");
    if(c.ticks<1||c.ticks>250000||c.substeps<1||c.substeps>1000||c.ticks*c.Tc>120||static_cast<long long>(c.ticks)*c.substeps>5000000)throw std::invalid_argument("simulation budget exceeded");
    static const std::set<std::string> cases{"nominal","pulse","bias","sustained","zero_voltage","stuck_positive","drag","fixed"};
    if(!cases.contains(c.scenario))throw std::invalid_argument("unknown scenario");
    validate(c.plant,c.Tc/c.substeps);validate(c.nominal,.000001);
    if(c.scenario=="drag") {auto effective=c.plant;effective.b*=c.drag_multiplier;validate(effective,c.Tc/c.substeps);}
    bound(c.initial[theta],-3.141592653589793,3.141592653589793);bound(c.initial[body],-5,5);bound(c.initial[wheel]-c.initial[body],-200,200);bound(c.initial[current],-2.5,2.5);
    for(unsigned j=4;j<9;++j)if(c.initial[j]!=0)throw std::invalid_argument("initial quadratures must be zero");
}
Input schedule(const RunConfig& c,int tick,double command) {
    // Every event is an integer number of sample intervals; no floating time comparisons.
    const int second=static_cast<int>(std::llround(1/c.Tc));
    Input u{command,0,1};
    if(c.scenario=="fixed")return {c.fixed_voltage,c.external,1};
    if((c.scenario=="pulse"&&tick>=6*second&&tick<7*second)||
       (c.scenario=="zero_voltage"&&tick>=8*second&&tick<12*second)||
       (c.scenario=="sustained"&&tick>=2*second))u.external_torque=c.pulse;
    if(c.scenario=="zero_voltage"&&tick>=6*second)u.voltage=0;
    if(c.scenario=="stuck_positive"&&tick>=4*second)u.voltage=c.fault_voltage;
    if(c.scenario=="drag"&&tick>=4*second)u.bearing_multiplier=c.drag_multiplier;
    return u;
}
RunResult simulate(const RunConfig& c) {
    validate(c);RunResult result;result.samples.reserve(c.ticks+1);
    State x=c.initial;ControlMemory memory;const double E0=energy(x,c.plant),H0=momentum(x,c.plant),h=c.Tc/c.substeps;
    auto observe=[&](double time) {
        result.max_current=std::max(result.max_current,std::abs(x[current]));
        result.max_relative_speed=std::max(result.max_relative_speed,std::abs(x[wheel]-x[body]));
        result.max_energy_defect=std::max(result.max_energy_defect,std::abs(energy(x,c.plant)-E0-x[electrical]+x[copper]+x[bearing]-x[external_work]));
        result.max_momentum_defect=std::max(result.max_momentum_defect,std::abs(momentum(x,c.plant)-H0-x[impulse]));
        if(std::abs(x[current])>=2.5||std::abs(x[wheel]-x[body])>=200)result.excursion=true;
        if(time>=c.ticks*c.Tc-2-1e-12) {
            result.terminal_angle_error=std::max(result.terminal_angle_error,std::abs(x[theta]-c.target));
            result.terminal_body_speed=std::max(result.terminal_body_speed,std::abs(x[body]));
        }
    };
    observe(0);Input previous{};bool had_previous=false;
    for(int tick=0;tick<=c.ticks;++tick) {
        const double time=tick*c.Tc;auto ctrl=control(x,c.nominal,c.controller,memory,c.target,c.Tc);
        if(ctrl.trip&&!result.tripped)result.events.push_back("trip@"+std::to_string(tick));
        result.tripped=ctrl.trip;
        const auto u=schedule(c,tick,ctrl.commanded_voltage);
        if(had_previous&&(u.external_torque!=previous.external_torque||u.bearing_multiplier!=previous.bearing_multiplier||
           (c.scenario=="zero_voltage"&&tick==static_cast<int>(std::llround(6/c.Tc)))||
           (c.scenario=="stuck_positive"&&tick==static_cast<int>(std::llround(4/c.Tc)))))result.events.push_back("schedule@"+std::to_string(tick));
        previous=u;had_previous=true;result.samples.push_back({time,x,u,ctrl});
        if(tick==c.ticks)break;
        for(int sub=0;sub<c.substeps;++sub) {
            auto candidate=rk4(x,c.plant,u,h);
            bool valid=std::all_of(candidate.begin(),candidate.end(),[](double v){return std::isfinite(v);});
            valid=valid&&std::abs(candidate[theta])<=100&&std::abs(candidate[body])<=100&&std::abs(candidate[wheel])<=2000&&std::abs(candidate[current])<=50;
            if(!valid) {
                result.aborted=true;result.reason="numerical envelope exceeded; last admissible state retained";
                result.events.push_back("abort@step"+std::to_string(result.completed_steps));
                if(sub>0)result.samples.push_back({time+sub*h,x,u,ctrl});
                return result;
            }
            x=candidate;++result.completed_steps;observe(time+(sub+1)*h);
        }
    }
    result.success=c.ticks*c.Tc>=2&&!result.aborted&&!result.tripped&&!result.excursion&&result.terminal_angle_error<=.01&&result.terminal_body_speed<=.002;
    return result;
}
}
