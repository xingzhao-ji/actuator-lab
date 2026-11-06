#include "actuator/simulation.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace actuator;
int main(){
 int failed=0,count=0;auto check=[](bool b){if(!b)throw std::runtime_error("contract failed");};
 auto test=[&](const char*n,auto f){++count;try{f();std::cout<<"PASS "<<n<<'\n';}catch(const std::exception&e){++failed;std::cout<<"FAIL "<<n<<": "<<e.what()<<'\n';}};
 auto rejects=[&](auto f){bool thrown=false;try{f();}catch(const std::exception&){thrown=true;}check(thrown);};
 test("pulse begins and ends exactly on sampled boundary",[&]{RunConfig c;c.scenario="pulse";check(schedule(c,599,0).external_torque==0);check(schedule(c,600,0).external_torque==.01);check(schedule(c,699,0).external_torque==.01);check(schedule(c,700,0).external_torque==0);});
 test("voltage failure and stuck driver ordering",[&]{RunConfig c;c.scenario="zero_voltage";check(schedule(c,599,5).voltage==5);check(schedule(c,600,5).voltage==0);c.scenario="stuck_positive";check(schedule(c,399,0).voltage==0);check(schedule(c,400,0).voltage==12);});
 test("complete event schedule participates in admission",[&]{RunConfig c;c.scenario="drag";c.plant.b=.1;rejects([&]{validate(c);});c={};c.pulse=.051;rejects([&]{validate(c);});c={};c.fault_voltage=12.1;rejects([&]{validate(c);});c={};c.Tc=.013;rejects([&]{validate(c);});});
 test("last RK stage uses left-held input at fault edge",[&]{RunConfig c;c.scenario="zero_voltage";c.ticks=601;auto result=simulate(c);const auto&a=result.samples[599];auto x=a.state;for(int j=0;j<c.substeps;++j)x=rk4(x,c.plant,a.input,c.Tc/c.substeps);for(unsigned j=0;j<9;++j)check(std::abs(x[j]-result.samples[600].state[j])<1e-13);check(result.samples[600].input.voltage==0);});
 test("zero voltage allows physical current continuity",[&]{RunConfig c;c.scenario="fixed";c.fixed_voltage=0;c.external=0;c.initial[current]=1;c.ticks=1;auto r=simulate(c);check(r.samples.front().state[current]==1);check(r.samples.back().state[current]>0&&r.samples.back().state[current]<1);});
 test("stuck voltage overrides trip without clipping state",[&]{RunConfig c;c.scenario="stuck_positive";c.ticks=600;auto r=simulate(c);check(r.tripped&&r.excursion&&r.max_current>2.5);bool seen=false;for(auto&s:r.samples)if(s.time>4&&s.control.trip&&s.input.voltage==12)seen=true;check(seen&&!r.success);});
 test("short trace cannot pass terminal window",[&]{RunConfig c;c.target=0;c.ticks=10;auto r=simulate(c);check(!r.success&&r.samples.size()==11);});
 test("nonphysical input rejected before integration",[&]{RunConfig c;c.initial[current]=2.51;rejects([&]{simulate(c);});c={};c.substeps=1;rejects([&]{simulate(c);});c={};c.scenario="unknown";rejects([&]{simulate(c);});});
 std::cout<<"RESULT "<<count-failed<<" passed "<<failed<<" failed\n";return failed?1:0;
}
