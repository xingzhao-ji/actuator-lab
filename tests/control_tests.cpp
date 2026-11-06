#include "actuator/control.hpp"
#include <cmath>
#include <functional>
#include <iostream>
#include <stdexcept>
using namespace actuator;
int main() {
 int failures=0,count=0;
 auto check=[](bool b){if(!b)throw std::runtime_error("contract failed");};
 auto test=[&](const char* n,auto f){++count;try{f();std::cout<<"PASS "<<n<<'\n';}catch(const std::exception& e){++failures;std::cout<<"FAIL "<<n<<": "<<e.what()<<'\n';}};
 test("positive body error commands positive wheel torque",[&]{State x{};x[theta]=.1;ControlMemory m;auto c=control(x,{},ControllerKind::direct,m,0,.01);check(std::abs(c.commanded_voltage-.48)<1e-14);check(x[theta]==.1);});
 test("both voltage rails and current demand bounded",[&]{for(int sign:{-1,1}){State x{};x[theta]=sign*3.;ControlMemory m;auto c=control(x,{},ControllerKind::direct,m,0,.01);check(c.commanded_voltage==sign*12.&&c.voltage_clamp);m={};c=control(x,{},ControllerKind::cascaded,m,0,.01);check(c.current_reference==sign*2.&&c.current_clamp);}});
 test("speed gate inhibits outward torque but allows braking",[&]{State x{};x[theta]=.1;x[wheel]=160;ControlMemory m;auto c=control(x,{},ControllerKind::direct,m,0,.01);check(c.speed_gate&&c.commanded_voltage==0);x[theta]=-.1;c=control(x,{},ControllerKind::direct,m,0,.01);check(!c.speed_gate&&c.commanded_voltage<0);});
 test("PI freezes at upper rail for outward error",[&]{State x{};x[theta]=3;x[wheel]=140;ControlMemory m{1,false};auto c=control(x,{},ControllerKind::cascaded,m,0,.01);check(c.voltage_clamp&&m.integral==1);});
 test("PI freezes at lower rail for outward error",[&]{State x{};x[theta]=-3;x[wheel]=-140;ControlMemory m{-1,false};auto c=control(x,{},ControllerKind::cascaded,m,0,.01);check(c.voltage_clamp&&m.integral==-1);});
 test("PI permits integration recovering from rail",[&]{State x{};x[current]=1;ControlMemory m{3,false};auto c=control(x,{},ControllerKind::cascaded,m,0,.01);check(c.commanded_voltage==12&&m.integral==2.99);});
 test("hard current trip latches zero terminal command and freezes PI",[&]{State x{};x[current]=2.5;ControlMemory m{.3,false};auto c=control(x,{},ControllerKind::cascaded,m,0,.01);check(c.trip&&c.commanded_voltage==0&&m.integral==.3&&x[current]==2.5);x={};c=control(x,{},ControllerKind::cascaded,m,1,.01);check(c.trip&&c.commanded_voltage==0&&m.integral==.3);});
 test("relative speed, not absolute wheel speed, determines hard trip",[&]{State x{};x[body]=3;x[wheel]=202;ControlMemory m;auto c=control(x,{},ControllerKind::direct,m,0,.01);check(!c.trip);x[wheel]=203;c=control(x,{},ControllerKind::direct,m,0,.01);check(c.trip);});
 test("feedforward ablation removes current feedback and PI update only",[&]{State x{};x[theta]=.1;x[wheel]=50;ControlMemory m{.2,false};auto c=control(x,{},ControllerKind::feedforward,m,0,.01);check(std::abs(c.commanded_voltage-3)<1e-14&&std::abs(c.current_reference-.25)<1e-14&&m.integral==.2);x[current]=2.5;c=control(x,{},ControllerKind::feedforward,m,0,.01);check(c.trip&&c.commanded_voltage==0);});
 std::cout<<"RESULT "<<count-failures<<" passed "<<failures<<" failed\n";return failures?1:0;
}
