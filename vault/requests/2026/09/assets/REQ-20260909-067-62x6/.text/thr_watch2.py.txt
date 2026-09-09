import os, sys, time, collections
pid=sys.argv[1]; dur=float(sys.argv[2]); t0=time.time(); prev={}
while time.time()-t0<dur:
    rows=[]
    for tid in os.listdir(f"/proc/{pid}/task"):
        try:
            w=open(f"/proc/{pid}/task/{tid}/wchan").read().strip()
            st=open(f"/proc/{pid}/task/{tid}/stat").read().rsplit(")",1)[1].split()
            state=st[0]; cpu=int(st[11])+int(st[12])
            d=cpu-prev.get(tid,cpu); prev[tid]=cpu
            rows.append((state,w or "-",d))
        except OSError as e: rows.append(("ERR",repr(e)[:30],0))
    c=collections.Counter((r[0],r[1]) for r in rows); busy=sum(r[2] for r in rows)
    print(f"{time.time()-t0:5.1f}s threads={len(rows)} cpu_ticks/s={busy} "+" ".join(f"{k[0]}:{k[1]}x{v}" for k,v in sorted(c.items(), key=lambda kv:-kv[1])), flush=True)
    time.sleep(1.0)
