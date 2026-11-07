"""Independent scalar adaptive solver, synthetic reference physics and kinematic controls."""
import math
import numpy as np
from scipy.integrate import solve_ivp

from flight import EVENTS


def solve(v0, acceleration, cfg):
    o,p,s=cfg["official"],cfg["physics"],cfg["solver"]
    def gate(t,state): return state[0]-o["gate"]
    def ground(t,state): return state[2]-p["radius"]
    gate.direction,ground.direction=1,-1
    gate.terminal=ground.terminal=True
    def rhs(t,state):
        return np.r_[state[3:],acceleration(t,state[3:])]
    sol=solve_ivp(rhs,(0,s["horizon"]),np.r_[o["r0"],v0],method="DOP853",
                  rtol=s["reference_rtol"],atol=s["reference_atol"],
                  events=[ground,gate],dense_output=True,max_step=.04)
    if not sol.success: raise RuntimeError(sol.message)
    if len(sol.t_events[0]):
        return sol,2,None,float(sol.t_events[0][0])
    if len(sol.t_events[1]):
        y,z=sol.y_events[1][0][1:3]
        inside=abs(y)<o["half_width"] and 0<z<o["height"]
        return sol,(0 if inside else 1),[float(y),float(z)],float(sol.t_events[1][0])
    return sol,3,None,None


def synthetic(split,cfg):
    spec=cfg["study"]
    seeds=np.random.SeedSequence(spec["seeds"][split]).spawn(spec[split]+1)
    order=np.random.default_rng(seeds[-1])
    labels=np.concatenate([order.permutation(3) for _ in range((spec[split]+2)//3)])[:spec[split]]
    data,outcomes=[],[]
    p=cfg["physics"]
    k=p["air_density"]*math.pi*p["radius"]**2/(2*p["mass"])
    for i,label in enumerate(labels):
        rng=np.random.default_rng(seeds[i])
        shot=f"{split}-{i+1:03d}"
        v0=rng.uniform([20,-11,2],[36,11,10])
        az=rng.uniform(0,2*np.pi); speed=2.5*np.sqrt(rng.random())
        wind=speed*np.array([np.cos(az),np.sin(az),0.])
        cap=[0,55,6][label]
        spin=rng.uniform(-cap,cap,3)
        offset=rng.uniform(0,.1)
        amp,period,phase=rng.uniform(2,5),rng.uniform(.18,.55),rng.uniform(0,2*np.pi)
        def truth(t,vel):
            u=vel-wind; speed=np.linalg.norm(u); unit=u/speed
            cd=.19+.20/(1+np.exp((speed-20)/2.5))+offset
            a=np.array([0.,0.,-p["g"]])-k*cd*speed*u
            cross=np.cross(spin,u); norm=np.linalg.norm(cross)
            if norm:
                cl=.32*np.tanh(4*p["radius"]*norm/speed**2)*np.exp(-.12*t)
                a+=k*cl*speed**2*cross/norm
            if label==2:
                angle=phase+2*np.pi*t/period
                force=amp*np.array([0,np.sin(angle),.4*np.cos(angle)])
                a+=force-unit*(force@unit)
            return a
        sol,e,q,t=solve(v0,truth,cfg)
        if sol.t[-1]<max(cfg["official"]["times"]): raise ValueError(f"missing required early frame: {shot}")
        f=sol.sol(cfg["official"]["times"])[:3].T
        quantum=cfg["observation"]["quantum_m"]
        readings=(np.floor(f/quantum+.5)*quantum).round(8)
        data.append({"id":shot,"xyz":readings.tolist()})
        outcomes.append({"id":shot,"family":["no_spin","stable_spin","wake"][label],"event":EVENTS[e],"yz":q,"T":t})
    return data,outcomes


def baselines(xyz,cfg):
    o,p=cfg["official"],cfg["physics"]
    t=np.array(o["times"]); dis=np.array(xyz)-o["r0"]
    g=np.array([0.,0.,-p["g"]])
    optical=(t@(dis-.5*t[:,None]**2*g))/(t@t)
    v,a=np.linalg.solve(np.column_stack((t,.5*t**2)),dis)
    summary={}
    for name,vel,acc in (("gravity",optical,g),("constant_a",v,a)):
        def times(a,b,c):
            out=np.roots([.5*a,b,c])
            return [float(s.real) for s in out if abs(s.imag)<1e-10 and 1e-9<s.real<=cfg["solver"]["horizon"]]
        gate=[s for s in times(acc[0],vel[0],-o["gate"]) if vel[0]+acc[0]*s>0]
        floor=[s for s in times(acc[2],vel[2],o["r0"][2]-p["radius"]) if vel[2]+acc[2]*s<0]
        tg=min(gate,default=np.inf);tf=min(floor,default=np.inf)
        if np.isfinite(tf) and tf<=tg: event,q,T=2,None,tf
        elif np.isfinite(tg):
            y,z=(np.array(o["r0"])+vel*tg+.5*acc*tg**2)[1:]
            event,q,T=int(not(abs(y)<o["half_width"] and 0<z<o["height"])),[float(y),float(z)],tg
        else: event,q,T=3,None,None
        summary[name]={"event":EVENTS[event],"point":q,"T":T}
    return summary


def numerical_checks(cfg):
    from flight import early,finish
    ph,o=cfg["physics"],cfg["official"]
    K=ph["air_density"]*math.pi*ph["radius"]**2/(2*ph["mass"])
    checks=[]
    for name,kind,vel,wind,drag,axis in [
        ("vacuum","D",[30,3,6],[0,0,0],0,[0,0,0]),
        ("drag_ground","D",[20,2,2],[1,0,0],.018,[0,0,0]),
        ("spin","S",[31,8,6],[0,1,0],.017,[.4,-.25,-.5]),
        ("empirical","E",[30,7,7],[1,-1,0],.1,[20,-35,12])]:
        wind=np.array(wind); axis=np.array(axis); vel=np.array(vel,dtype=float)
        def reference(t,v):
            u=v-wind; speed=np.linalg.norm(u)
            g=np.array([0.,0.,-ph["g"]])
            if kind!="E": return g-drag*speed*u+np.cross(axis,u)
            cross=np.cross(axis,u); cn=np.linalg.norm(cross)
            cd=.155+.346/(1+math.exp((min(29.9,max(9.3,speed))-12.19)/1.309))+drag
            cl=.38*math.tanh(5*ph["radius"]*cn/speed**2)
            return g-K*cd*speed*u+K*cl*speed**2*cross/max(cn,1e-20)
        sol,expected,q,t=solve(vel,reference,cfg)
        eta=(wind[None,:],np.array([drag]),axis[None,:])
        frames,speeds,_=early(vel[None,:],eta,kind,cfg)
        event,yz,arrival=finish(frames[-1],speeds[-1],eta,kind,cfg,o["times"][-1])
        pos_error=max(np.linalg.norm(f[0]-sol.sol(time)[:3]) for f,time in zip(frames,o["times"]))
        if q is not None: pos_error=max(pos_error,np.linalg.norm(yz[0]-q))
        if name=="vacuum":
            exact=o["gate"]/vel[0]
            expected_q=np.array(o["r0"])[1:]+vel[1:]*exact+[0,-.5*ph["g"]*exact**2]
            pos_error=max(pos_error,np.linalg.norm(yz[0]-expected_q))
        delta=abs(arrival[0]-t)
        passed=(int(event[0])==expected and pos_error<=cfg["study"]["reference_position_tol_m"]
                and delta<=cfg["study"]["reference_time_tol_s"])
        checks.append({"case":name,"event":EVENTS[expected],"error_m":float(pos_error),"error_s":float(delta),"pass":bool(passed)})
    return checks
