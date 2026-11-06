"""Independent reduced-coordinate reference. No C++ bindings or shared RHS."""
import numpy as np
from scipy.linalg import expm
from scipy.integrate import solve_ivp

DEFAULT = {"Jb":.05,"Jw":.001,"R":2.,"L":.01,"k":.05,"b":1e-5}

def exact_constant(initial, plant, voltage, external, duration):
    """Affine matrix solution in [theta,H,r,i,1]; returns four physical states."""
    Jb,Jw,R,L,k,b=(plant[n] for n in ("Jb","Jw","R","L","k","b"))
    total=Jb+Jw;reduced=Jb*Jw/total
    A=np.zeros((5,5))
    A[0,1:3]=[1/total,-Jw/total]
    A[1,4]=external
    A[2,2:5]=[-b/reduced,k/reduced,-external/Jb]
    A[3,2:5]=[-k/L,-R/L,voltage/L]
    z=expm(A*duration)@np.array([initial[0],Jb*initial[1]+Jw*initial[2],initial[2]-initial[1],initial[3],1.])
    wb=(z[1]-Jw*z[2])/total
    return np.array([z[0],wb,wb+z[2],z[3]])

def reference_command(theta,wb,r,current,target,kind,memory,Tc):
    """Separate sampled controller implementation, with fixed nominal gains."""
    z,tripped=memory
    tripped=tripped or abs(current)>=2.5 or abs(r)>=200
    if tripped:return 0.,(z,True)
    request=.12*(theta-target)+.16*wb
    if abs(r)>=150 and request*r>0:request=0
    if kind=="direct":return float(np.clip(40*request,-12,12)),(z,False)
    demand=float(np.clip((request+1e-5*r)/.05,-2,2))
    if kind=="feedforward":return float(np.clip(2*demand+.05*r,-12,12)),(z,False)
    error=demand-current
    raw=2*demand+.05*r+.5*error+5*z
    if -12<=raw<=12 or (raw>12 and error<0) or (raw< -12 and error>0):z+=Tc*error
    return float(np.clip(raw,-12,12)),(z,False)

def reference_integrate(config, voltage_schedule=None, rtol=1e-11, atol=1e-12):
    p=config["plant"];Jb,Jw,R,L,k,b=(p[n] for n in ("Jb","Jw","R","L","k","b"))
    total=Jb+Jw;reduced=Jb*Jw/total;Tc=config["Tc"];ticks=config["ticks"]
    initial=np.array(config["initial"],dtype=float)
    z=initial.copy();z[1]=Jb*initial[1]+Jw*initial[2];z[2]=initial[2]-initial[1]
    def physical(v):
        x=v.copy();x[1]=(v[1]-Jw*v[2])/total;x[2]=x[1]+v[2];return x
    states=[physical(z)];voltages=[];memory=(0.,False);trips=[]
    for tick in range(ticks):
        wb=(z[1]-Jw*z[2])/total
        voltage,memory=reference_command(z[0],wb,z[2],z[3],config["target"],config["controller"],memory,Tc)
        trips.append(memory[1]);name=config["scenario"];t=tick*Tc
        ext=0.;drag=b
        if name=="fixed":voltage=config["fixed_voltage"];ext=config["external"]
        if name=="pulse" and 6-1e-10<=t<7-1e-10:ext=config["pulse"]
        if name=="sustained" and t>=2-1e-10:ext=config["pulse"]
        if name=="zero_voltage":
            if t>=6-1e-10:voltage=0
            if 8-1e-10<=t<12-1e-10:ext=config["pulse"]
        if name=="stuck_positive" and t>=4-1e-10:voltage=config["fault_voltage"]
        if name=="drag" and t>=4-1e-10:drag=b*config["drag_multiplier"]
        if voltage_schedule is not None:voltage=float(voltage_schedule[tick])
        voltages.append(voltage)
        def derivative(_,v):
            angle,H,r,i=v[:4];body_rate=(H-Jw*r)/total
            return [body_rate,ext,(k*i-drag*r)/reduced-ext/Jb,
                    (voltage-R*i-k*r)/L,voltage*i,R*i*i,drag*r*r,ext*body_rate,ext]
        solution=solve_ivp(derivative,(0,Tc),z,method="DOP853",rtol=rtol,atol=atol,t_eval=[Tc])
        if not solution.success:raise RuntimeError(solution.message)
        z=solution.y[:,-1];states.append(physical(z))
    return {"states":np.asarray(states),"voltage":np.asarray(voltages),"trips":np.asarray(trips),"rtol":rtol,"atol":atol}
