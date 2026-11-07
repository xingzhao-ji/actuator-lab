#include "actuator/simulation.hpp"
#include <charconv>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <stdexcept>
#include <unistd.h>
using namespace actuator;
namespace fs=std::filesystem;
namespace {
double number(const std::string& s) {
    double value;const auto [end,error]=std::from_chars(s.data(),s.data()+s.size(),value);
    if(error!=std::errc{}||end!=s.data()+s.size()||!std::isfinite(value))throw std::invalid_argument("invalid finite number");
    return value;
}
int integer(const std::string& s) {
    int value;const auto [end,error]=std::from_chars(s.data(),s.data()+s.size(),value);
    if(error!=std::errc{}||end!=s.data()+s.size())throw std::invalid_argument("invalid integer");return value;
}
template<class T> void write_nullable(std::ostream& out,const std::optional<T>& value) {
    if(value)out<<*value;else out<<"null";
}
void write_metrics(std::ostream& out,const ObservationalMetrics& m) {
    out<<"{\"schema_version\":"<<m.schema_version
        <<",\"units\":{\"time\":\"s\",\"energy\":\"J\",\"gate_fraction\":\"dimensionless\"}"
        <<",\"tracking_settling_status\":\""<<m.tracking_settling_status<<"\",\"tracking_settling_time_s\":";
    write_nullable(out,m.tracking_settling_time_s);
    out<<",\"observation_step_s\":"<<m.observation_step_s<<",\"completed_steps\":"<<m.completed_steps
        <<",\"observed_duration_s\":"<<m.observed_duration_s<<",\"planned_duration_s\":"<<m.planned_duration_s
        <<",\"supplied_energy_J\":"<<m.supplied_energy_J<<",\"regenerated_energy_J\":"<<m.regenerated_energy_J
        <<",\"net_electrical_work_J\":"<<m.net_electrical_work_J<<",\"energy_split_residual_J\":"<<m.energy_split_residual_J
        <<",\"last_violating_step\":";
    write_nullable(out,m.last_violating_step);
    out<<",\"qualifying_tail_start_step\":";write_nullable(out,m.qualifying_tail_start_step);
    out<<",\"gate_durations_s\":{";
    for(unsigned j=0;j<4;++j){if(j)out<<',';out<<'"'<<metric_gate_names[j]<<"\":"<<m.gate_durations_s[j];}
    out<<"},\"gate_fractions\":{";
    for(unsigned j=0;j<4;++j){if(j)out<<',';out<<'"'<<metric_gate_names[j]<<"\":";write_nullable(out,m.gate_fractions[j]);}
    out<<"}}";
}
void write_result(const fs::path& output,const RunConfig& c,const RunResult& r) {
    if(output.filename().empty()||fs::exists(output)||!fs::is_directory(output.parent_path().empty()?fs::path("."):output.parent_path()))throw std::invalid_argument("output must be a new directory in an existing parent");
    const fs::path temp=output.string()+".tmp-"+std::to_string(getpid());
    if(!fs::create_directory(temp))throw std::runtime_error("temporary output already exists");
    try {
        std::ofstream trace;trace.exceptions(std::ios::badbit|std::ios::failbit);trace.open(temp/"trace.csv");trace<<std::setprecision(17);
        trace<<"time,theta,omega_body,omega_wheel,current,W_e,Q_R,Q_b,W_ext,I_ext,voltage,external_torque,bearing_multiplier,requested_voltage,command_voltage,current_reference,speed_gate,current_clamp,voltage_clamp,trip\n";
        for(const auto& s:r.samples) {
            trace<<s.time;for(double v:s.state)trace<<','<<v;
            trace<<','<<s.input.voltage<<','<<s.input.external_torque<<','<<s.input.bearing_multiplier<<','<<s.control.requested_voltage<<','<<s.control.commanded_voltage<<','<<s.control.current_reference<<','<<s.control.speed_gate<<','<<s.control.current_clamp<<','<<s.control.voltage_clamp<<','<<s.control.trip<<'\n';
        }
        trace.close();
        std::ofstream json;json.exceptions(std::ios::badbit|std::ios::failbit);json.open(temp/"summary.json");json<<std::setprecision(17)<<std::boolalpha;
        json<<"{\n\"schema_version\":1,\n\"config\":{\"scenario\":\""<<c.scenario<<"\",\"controller\":\""<<(c.controller==ControllerKind::direct?"direct":c.controller==ControllerKind::cascaded?"cascaded":"feedforward")<<"\",\"ticks\":"<<c.ticks<<",\"substeps\":"<<c.substeps<<",\"Tc\":"<<c.Tc<<",\"target\":"<<c.target
            <<",\"pulse\":"<<c.pulse<<",\"fixed_voltage\":"<<c.fixed_voltage<<",\"external\":"<<c.external<<",\"fault_voltage\":"<<c.fault_voltage<<",\"drag_multiplier\":"<<c.drag_multiplier
            <<",\"plant\":{\"Jb\":"<<c.plant.Jb<<",\"Jw\":"<<c.plant.Jw<<",\"R\":"<<c.plant.R<<",\"L\":"<<c.plant.L<<",\"k\":"<<c.plant.k<<",\"b\":"<<c.plant.b<<"},\"initial\":[";
        for(unsigned j=0;j<9;++j){if(j)json<<',';json<<c.initial[j];}
        json<<"]},\n\"aborted\":"<<r.aborted<<",\"tripped\":"<<r.tripped<<",\"success\":"<<r.success<<",\"excursion\":"<<r.excursion<<",\"reason\":\""<<r.reason<<"\",\n\"completed_steps\":"<<r.completed_steps
            <<",\"max_current\":"<<r.max_current<<",\"max_relative_speed\":"<<r.max_relative_speed<<",\"max_energy_defect\":"<<r.max_energy_defect<<",\"max_momentum_defect\":"<<r.max_momentum_defect<<",\"terminal_angle_error\":"<<r.terminal_angle_error<<",\"terminal_body_speed\":"<<r.terminal_body_speed<<",\"events\":[";
        for(unsigned j=0;j<r.events.size();++j){if(j)json<<',';json<<'"'<<r.events[j]<<'"';}json<<"],\n\"observational_metrics\":";write_metrics(json,r.observational_metrics);json<<"\n}\n";json.close();
        // Both artifacts become visible together; an existing directory is never replaced.
        if(fs::exists(output))throw std::runtime_error("output appeared during run");
        fs::rename(temp,output);
    }catch(...){std::error_code ignored;fs::remove_all(temp,ignored);throw;}
}
}
int main(int argc,char** argv) {
    try {
        if(argc<2||std::string(argv[1])!="simulate"||(argc-2)%2!=0)throw std::invalid_argument("usage: actuator_lab simulate --output NEW_DIRECTORY [--scenario NAME --controller direct|cascaded|feedforward --ticks N --substeps N --Tc SECONDS --target RAD ...]");
        std::map<std::string,std::string> options;
        for(int j=2;j<argc;j+=2)if(!options.emplace(argv[j],argv[j+1]).second)throw std::invalid_argument("duplicate option");
        RunConfig c;
        if(options.contains("--scenario"))c.scenario=options.at("--scenario");
        if(c.scenario=="sustained")c.ticks=3000;
        if(c.scenario=="bias"||c.scenario=="drag")c.initial[wheel]=120;
        fs::path output;
        for(const auto& [key,value]:options) {
            if(key=="--output")output=value;
            else if(key=="--scenario"){}
            else if(key=="--controller") {if(value=="direct")c.controller=ControllerKind::direct;else if(value=="cascaded")c.controller=ControllerKind::cascaded;else if(value=="feedforward")c.controller=ControllerKind::feedforward;else throw std::invalid_argument("unknown controller");}
            else if(key=="--ticks")c.ticks=integer(value);
            else if(key=="--substeps")c.substeps=integer(value);
            else {
                const double v=number(value);
                if(key=="--Jb")c.plant.Jb=v;else if(key=="--Jw")c.plant.Jw=v;else if(key=="--R")c.plant.R=v;else if(key=="--L")c.plant.L=v;else if(key=="--k")c.plant.k=v;else if(key=="--b")c.plant.b=v;
                else if(key=="--theta0")c.initial[theta]=v;else if(key=="--wb0")c.initial[body]=v;else if(key=="--ww0")c.initial[wheel]=v;else if(key=="--i0")c.initial[current]=v;
                else if(key=="--target")c.target=v;else if(key=="--Tc")c.Tc=v;else if(key=="--pulse")c.pulse=v;else if(key=="--fixed-voltage")c.fixed_voltage=v;else if(key=="--external")c.external=v;else if(key=="--fault-voltage")c.fault_voltage=v;else if(key=="--drag-multiplier")c.drag_multiplier=v;
                else throw std::invalid_argument("unknown option");
            }
        }
        if(output.empty()||fs::exists(output)||!fs::is_directory(output.parent_path().empty()?fs::path("."):output.parent_path()))throw std::invalid_argument("output must be new and have an existing parent");
        const auto result=simulate(c);write_result(output,c,result);
        std::cout<<"status="<<(result.aborted?"aborted":"completed")<<" success="<<result.success<<" samples="<<result.samples.size()<<'\n';return result.aborted?3:0;
    }catch(const std::exception& e){std::cerr<<"error: "<<e.what()<<'\n';return 2;}
}
