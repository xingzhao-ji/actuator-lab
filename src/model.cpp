#include "actuator/model.hpp"
#include <stdexcept>
#include <algorithm>
#include <cmath>
namespace actuator {
State rhs(const State& x,const Params& p,const Input& u) {
    const double r=x[wheel]-x[body], drag=p.b*u.bearing_multiplier*r;
    const double torque=p.k*x[current]-drag;
    return {x[body],(u.external_torque-torque)/p.Jb,torque/p.Jw,
        (u.voltage-p.R*x[current]-p.k*r)/p.L,
        u.voltage*x[current],p.R*x[current]*x[current],drag*r,
        u.external_torque*x[body],u.external_torque};
}
State rk4(const State& x,const Params& p,const Input& u,double h) {
    return rk4(x,p,u,h,nullptr);
}
State rk4(const State& x,const Params& p,const Input& u,double h,RKStages* stages) {
    auto add=[&](const State& a,double factor) { State v=x;for(unsigned j=0;j<9;++j)v[j]+=factor*a[j];return v; };
    const auto a=rhs(x,p,u),b=rhs(add(a,h/2),p,u),c=rhs(add(b,h/2),p,u),d=rhs(add(c,h),p,u);
    if(stages)stages->currents={x[current],x[current]+(h/2)*a[current],
        x[current]+(h/2)*b[current],x[current]+h*c[current]};
    State v=x;for(unsigned j=0;j<9;++j)v[j]+=h/6*(a[j]+2*b[j]+2*c[j]+d[j]);return v;
}
double energy(const State& x,const Params& p) {return .5*(p.Jb*x[body]*x[body]+p.Jw*x[wheel]*x[wheel]+p.L*x[current]*x[current]);}
double momentum(const State& x,const Params& p) {return p.Jb*x[body]+p.Jw*x[wheel];}
void validate(const Params& p,double h) {
    auto bound=[](double v,double lo,double hi){if(!std::isfinite(v)||v<lo||v>hi)throw std::invalid_argument("parameter outside finite admitted bounds");};
    bound(p.Jb,.001,10);bound(p.Jw,1e-6,1);bound(p.R,.1,100);bound(p.L,1e-5,1);bound(p.k,.0001,1);bound(p.b,0,.1);
    const double Jeff=p.Jb*p.Jw/(p.Jb+p.Jw);
    double scale=std::min(p.L/p.R,std::sqrt(p.L*Jeff)/p.k);
    if(p.b>0)scale=std::min(scale,Jeff/p.b);
    if(!std::isfinite(h)||h<=0||h>.25*scale)throw std::invalid_argument("step exceeds electrical/mechanical timescale admission");
}
}
