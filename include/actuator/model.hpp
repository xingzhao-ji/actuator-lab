#pragma once
#include <array>

namespace actuator {
enum Index { theta=0, body=1, wheel=2, current=3, electrical=4, copper=5,
             bearing=6, external_work=7, impulse=8 };
using State = std::array<double,9>;
struct Params { double Jb=0.05,Jw=0.001,R=2,L=0.01,k=0.05,b=1e-5; };
struct Input { double voltage=0,external_torque=0,bearing_multiplier=1; };
State rhs(const State&,const Params&,const Input&);
State rk4(const State&,const Params&,const Input&,double h);
double energy(const State&,const Params&);
double momentum(const State&,const Params&);
void validate(const Params&,double h);
}
