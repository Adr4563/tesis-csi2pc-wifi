#!/usr/bin/env python3
# Genera trafico para CSI ~97/s: ping ICMP a ritmo fijo hacia la laptop.
# El router reenvia las respuestas a la Pi POR AIRE -> los ESP32 las sniffean.
import sys, subprocess, time
DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
TARGET = sys.argv[2] if len(sys.argv) > 2 else '192.168.0.75'   # laptop (responde ICMP)
# -i 0.006 ~166 pkt/s -> ~97 CSI/s tras agregacion del router. -s 0 paquetes minimos.
p = subprocess.Popen(['sudo','-n','ping','-i','0.006','-s','0',TARGET],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(DUR)
finally:
    p.terminate()
    try: subprocess.run(['sudo','-n','kill',str(p.pid)], timeout=2)
    except Exception: pass
