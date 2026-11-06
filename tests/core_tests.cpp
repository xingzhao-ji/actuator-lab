#include "actuator/model.hpp"
#include <cmath>
#include <functional>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
using namespace actuator;
namespace {
int passed=0,failed=0;
void check(bool condition,const std::string& message) { if(!condition)throw std::runtime_error(message); }
void near(double value,double expected,double tolerance,const std::string& message) {
    if(!std::isfinite(value)||std::abs(value-expected)>tolerance)
        throw std::runtime_error(message+" actual="+std::to_string(value)+" expected="+std::to_string(expected));
}
void test(const char* name,const std::function<void()>& operation) {
    try { operation();++passed;std::cout<<"PASS "<<name<<'\n'; }
    catch(const std::exception& e) { ++failed;std::cout<<"FAIL "<<name<<": "<<e.what()<<'\n'; }
}
void rejects(const std::function<void()>& f) { bool threw=false;try{f();}catch(const std::exception&){threw=true;}check(threw,"invalid input accepted"); }
State integrate(State x,const Params& p,const Input& u,double h,int n) { for(int j=0;j<n;++j)x=rk4(x,p,u,h);return x; }
}
int main() {
    test("literal coupled derivatives and signed work",[]{
        Params p;State x{.2,.3,10.3,.8,0,0,0,0,0};auto d=rhs(x,p,{3,.01,1});
        const State expected{.3,-.598,39.9,90,2.4,1.28,.001,.003,.01};
        for(unsigned j=0;j<9;++j)near(d[j],expected[j],1e-12,"literal derivative");
    });
    test("co-rotation has no back EMF or bearing torque",[]{
        State x{};x[body]=2;x[wheel]=2;auto d=rhs(x,{},{});
        near(d[current],0,0,"absolute rate incorrectly used for EMF");near(d[body],0,0,"co-rotation torque");near(d[theta],2,0,"angle kinematics");
    });
    test("zero input rest stays stationary",[]{
        auto x=integrate({}, {}, {},.0005,100);for(double v:x)near(v,0,0,"rest drift");
    });
    test("RL circuit analytic transient",[]{
        Params p;p.k=0;p.b=0;State x{};x[current]=.1;
        x=integrate(x,p,{1,0,1},.0001,250);
        near(x[current],.5+(.1-.5)*std::exp(-5),1e-10,"RL exponential");
    });
    test("friction-only exchange analytic solution",[]{
        Params p;p.k=0;p.b=.002;State x{};x[theta]=.1;x[body]=-.2;x[wheel]=9.8;
        const double H=p.Jb*x[body]+p.Jw*x[wheel],a=p.b*(1/p.Jb+1/p.Jw),T=.5,r=10*std::exp(-a*T);
        x=integrate(x,p,{},.0005,1000);
        near(x[wheel]-x[body],r,1e-10,"friction decay");near(momentum(x,p),H,1e-13,"internal friction lost momentum");
        near(x[theta],.1+H/(p.Jb+p.Jw)*T-p.Jw/(p.Jb+p.Jw)*10*(1-std::exp(-a*T))/a,1e-11,"analytic body angle");
    });
    test("external torque includes impulse and body work",[]{
        Params p;p.k=0;p.b=0;State initial{};initial[theta]=.3;initial[body]=.1;initial[wheel]=3;
        auto x=integrate(initial,p,{0,.005,1},.0005,2000);
        near(x[body],.2,1e-12,"external acceleration");near(x[theta],.45,1e-12,"external angle");
        near(momentum(x,p)-momentum(initial,p),x[impulse],1e-12,"impulse ledger");
        near(energy(x,p)-energy(initial,p),x[external_work],1e-12,"external work missing");check(x[external_work]>0,"nonzero work fixture");
    });
    test("derivative identities across finite states",[]{
        Params p;
        for(int n=-10;n<=10;++n) {
            State x{};x[body]=n*.03;x[wheel]=n*7.1;x[current]=n*.14;Input u{n*.7,n*.002,3};auto d=rhs(x,p,u);
            near(p.Jb*d[body]+p.Jw*d[wheel],u.external_torque,1e-14,"momentum derivative");
            const double de=p.Jb*x[body]*d[body]+p.Jw*x[wheel]*d[wheel]+p.L*x[current]*d[current];
            near(de,d[electrical]-d[copper]-d[bearing]+d[external_work],1e-12,"energy derivative");
            check(d[copper]>=0&&d[bearing]>=0,"negative loss");
        }
    });
    test("wrong reaction torque mutant is detected",[]{
        Params p;State x{};x[current]=1;auto d=rhs(x,p,{});
        const double wrong_body=(p.k*x[current])/p.Jb;
        check(std::abs(p.Jb*wrong_body+p.Jw*d[wheel])>.09,"identity missed wrong sign");
    });
    test("coupled integrated work balance",[]{
        Params p;auto x=integrate({},p,{3,.01,1},.0005,200);
        near(energy(x,p)-x[electrical]+x[copper]+x[bearing]-x[external_work],0,2e-7,"integrated work defect");
        near(momentum(x,p),x[impulse],1e-12,"integrated momentum");
    });
    test("parameter and resolution admission",[]{
        Params p;validate(p,.0005);rejects([&]{validate(p,.01);});
        p.Jb=0;rejects([&]{validate(p,.0005);});p={};p.k=0;rejects([&]{validate(p,.0005);});
        p={};p.L=std::numeric_limits<double>::quiet_NaN();rejects([&]{validate(p,.0005);});
    });
    std::cout<<"RESULT "<<passed<<" passed "<<failed<<" failed\n";return failed?1:0;
}
