#include "actuator/metrics.hpp"
#include "actuator/simulation.hpp"
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace actuator;
int main() {
 int failed=0,count=0;
 auto check=[](bool value){if(!value)throw std::runtime_error("contract failed");};
 auto near=[&](double a,double b){check(std::abs(a-b)<1e-12);};
 auto test=[&](const char* name,auto f){++count;try{f();std::cout<<"PASS "<<name<<'\n';}catch(const std::exception& e){++failed;std::cout<<"FAIL "<<name<<": "<<e.what()<<'\n';}};
 State good{},bad{};bad[theta]=.02;
 const RKStages zero{{0,0,0,0}};
 auto append=[&](MetricAccumulator& m,const State& state,const ControlResult& flags=ControlResult{}){m.accept(state,flags,0,zero);};
 test("initial in-band point settles at zero with exactly two seconds",[&]{MetricAccumulator m(.5,4,0,good);for(int j=0;j<4;++j)append(m,good);auto r=m.finish(false,0);check(r.tracking_settling_status=="settled");near(*r.tracking_settling_time_s,0);check(!r.last_violating_step&&r.qualifying_tail_start_step==0);});
 test("late violation resets to next endpoint and exact two second tail qualifies",[&]{MetricAccumulator m(.5,7,0,good);append(m,good);append(m,bad);for(int j=0;j<5;++j)append(m,good);auto r=m.finish(false,0);check(r.tracking_settling_status=="settled");near(*r.tracking_settling_time_s,1.5);check(r.last_violating_step==2&&r.qualifying_tail_start_step==3);});
 test("one accepted step short never fabricates dwell",[&]{MetricAccumulator m(.5,6,0,good);append(m,good);append(m,bad);for(int j=0;j<4;++j)append(m,good);auto r=m.finish(false,0);check(r.tracking_settling_status=="not_settled"&&!r.tracking_settling_time_s);check(r.qualifying_tail_start_step==3);});
 test("initial violation requires first qualifying endpoint",[&]{MetricAccumulator m(.5,5,0,bad);for(int j=0;j<5;++j)append(m,good);auto r=m.finish(false,0);near(*r.tracking_settling_time_s,.5);check(r.last_violating_step==0);});
 test("inclusive angle and rate boundaries qualify",[&]{State edge{};edge[theta]=.01;edge[body]=-.002;MetricAccumulator m(.5,4,0,edge);for(int j=0;j<4;++j)append(m,edge);check(m.finish(false,0).tracking_settling_status=="settled");});
 test("rate alone resets candidate and final violation has no tail",[&]{State fast{};fast[body]=.00201;MetricAccumulator m(.5,4,0,good);for(int j=0;j<3;++j)append(m,good);append(m,fast);auto r=m.finish(false,0);check(r.tracking_settling_status=="not_settled"&&!r.qualifying_tail_start_step&&r.last_violating_step==4);});
 test("short horizon status and incomplete prefix override apparent settling",[&]{MetricAccumulator short_run(.5,3,0,good);for(int j=0;j<3;++j)append(short_run,good);auto s=short_run.finish(false,0);check(s.tracking_settling_status=="insufficient_horizon"&&!s.tracking_settling_time_s);MetricAccumulator aborted(.5,8,0,good);for(int j=0;j<5;++j)append(aborted,good);auto a=aborted.finish(true,0);check(a.tracking_settling_status=="incomplete"&&!a.tracking_settling_time_s);near(a.observed_duration_s,2.5);near(a.planned_duration_s,4);check(a.completed_steps==5);});
 test("three of four left-held flags count overlapping durations",[&]{MetricAccumulator m(.5,4,0,good);ControlResult flags;flags.speed_gate=flags.current_clamp=flags.voltage_clamp=flags.trip=true;for(int j=0;j<3;++j)append(m,good,flags);append(m,good);auto r=m.finish(false,0);for(unsigned j=0;j<4;++j){near(r.gate_durations_s[j],1.5);near(*r.gate_fractions[j],.75);}});
 test("terminal-only trip on real simulation adds no occupancy",[&]{RunConfig c;c.scenario="fixed";c.fixed_voltage=12;c.external=0;c.ticks=1;auto r=simulate(c);check(!r.samples.front().control.trip&&r.samples.back().control.trip);check(r.tripped);near(r.observational_metrics.gate_durations_s[3],0);near(*r.observational_metrics.gate_fractions[3],0);});
 test("aborted partial interval uses actual accepted denominator",[&]{MetricAccumulator m(.5,8,0,good);ControlResult gate;gate.speed_gate=true;append(m,good,gate);append(m,good,gate);append(m,good);auto r=m.finish(true,0);near(r.gate_durations_s[0],1);near(*r.gate_fractions[0],2./3);check(r.completed_steps==3);});
 test("zero accepted duration has null fractions and incomplete status",[&]{MetricAccumulator m(.5,4,0,good);auto r=m.finish(true,0);for(auto f:r.gate_fractions)check(!f);check(!r.tracking_settling_time_s&&r.tracking_settling_status=="incomplete");near(r.observed_duration_s,0);});
 test("positive negative and zero held power have independent literal energies",[&]{MetricAccumulator m(.5,3,0,good);m.accept(good,{},2,RKStages{{3,3,3,3}});m.accept(good,{},-2,RKStages{{3,3,3,3}});m.accept(good,{},0,RKStages{{100,100,100,100}});auto r=m.finish(false,0);near(r.supplied_energy_J,3);near(r.regenerated_energy_J,3);near(r.energy_split_residual_J,0);});
 test("within-step crossing preserves both gross components when signed work cancels",[&]{MetricAccumulator m(1,1,0,good);m.accept(good,{},2,RKStages{{-1,0,0,1}});auto r=m.finish(false,0);near(r.supplied_energy_J,1./3);near(r.regenerated_energy_J,1./3);near(r.net_electrical_work_J,0);});
 test("observed rk4 preserves physical state bit values and exposes actual stage currents",[&]{State x{};x[current]=1;Params p;p.k=0;p.b=0;Input u{2,0,1};RKStages stages;auto a=rk4(x,p,u,.001);auto b=rk4(x,p,u,.001,&stages);check(a==b);for(auto i:stages.currents)near(i,1);MetricAccumulator m(.001,1,0,x);m.accept(b,{},u.voltage,stages);auto r=m.finish(false,b[electrical]);near(r.supplied_energy_J,.002);near(r.regenerated_energy_J,0);near(r.energy_split_residual_J,0);});
 test("analytic RL transient with current crossing agrees with independent integral",[&]{// i(t)=1-2 exp(-2t), V=2: zero crossing ln(2)/2.
 Params p;p.k=0;p.b=0;p.R=2;p.L=1;Input u{2,0,1};State x{};x[current]=-1;MetricAccumulator m(.001,1000,0,x);
 for(int j=0;j<1000;++j){RKStages stages;x=rk4(x,p,u,.001,&stages);m.accept(x,{},2,stages);}auto r=m.finish(false,x[electrical]);
 const double regenerated=1-std::log(2.),net=2*std::exp(-2.);
 check(std::abs(r.regenerated_energy_J-regenerated)<5e-7);check(std::abs(r.supplied_energy_J-(regenerated+net))<5e-7);near(r.energy_split_residual_J,0);
 });
 test("simulation integrates fault-adjusted voltage after controller trip",[&]{RunConfig c;c.scenario="stuck_positive";c.ticks=600;auto r=simulate(c);check(r.tripped);check(r.observational_metrics.completed_steps==r.completed_steps);check(r.observational_metrics.supplied_energy_J>0);near(r.observational_metrics.net_electrical_work_J,r.samples.back().state[electrical]);check(std::abs(r.observational_metrics.energy_split_residual_J)<1e-10);});
 std::cout<<"RESULT "<<count-failed<<" passed "<<failed<<" failed\n";return failed?1:0;
}
