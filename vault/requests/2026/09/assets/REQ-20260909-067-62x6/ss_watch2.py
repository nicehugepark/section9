import subprocess, time, sys
port=sys.argv[1]; dur=float(sys.argv[2]); t0=time.time(); seen={}; lq=[]
while time.time()-t0<dur:
    out=subprocess.run(["ss","-tanpH"],capture_output=True,text=True).stdout
    for ln in out.splitlines():
        c=ln.split()
        if len(c)<5: continue
        st,rq,sq,loc,rem=c[0],c[1],c[2],c[3],c[4]; owner="users" in ln
        if st=="LISTEN" and loc.endswith(":"+port): lq.append((round(time.time()-t0,2),rq)); continue
        if loc.endswith(":"+port):
            seen.setdefault(rem,[]).append((round(time.time()-t0,2),st,rq,owner))
    time.sleep(0.05)
print("listener accept-queue samples (nonzero):", [x for x in lq if x[1]!="0"][:40], "of", len(lq))
for k,v in sorted(seen.items(), key=lambda kv: kv[1][0][0]):
    tr=[]
    for x in v:
        if not tr or (tr[-1][1],tr[-1][3])!=(x[1],x[3]): tr.append(x)
    life=round(v[-1][0]-v[0][0],2)
    print(f" S {k:22s} life={life:5.2f}s", tr[:5])
