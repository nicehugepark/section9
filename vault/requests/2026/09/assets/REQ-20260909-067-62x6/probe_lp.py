import socket, sys, time
port=int(sys.argv[1]); n=int(sys.argv[2]); gap=float(sys.argv[3]); tag=sys.argv[4]
t0=time.time(); res=[]; ok=0; oth=[]
for i in range(n):
    st="connect"; lp=None
    try:
        c=socket.create_connection(("127.0.0.1",port),3.0); lp=c.getsockname()[1]; st="send"; c.sendall(b"GET /api/whoami HTTP/1.0\r\nHost: x\r\n\r\n"); c.settimeout(6); st="recv"; d=c.recv(4096); c.close()
        if d.startswith(b"HTTP/"): ok+=1
        else: oth.append((round(time.time()-t0,1),lp,"bad"))
    except ConnectionResetError: res.append((round(time.time()-t0,1),st,lp))
    except Exception as e: oth.append((round(time.time()-t0,1),st,lp,repr(e)[:40]))
    time.sleep(gap)
print(f"[{tag}] port={port} n={n} ok={ok} resets={len(res)} at={res} other={oth}", flush=True)
