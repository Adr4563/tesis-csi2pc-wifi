#!/usr/bin/env python3
# Captura CSI de los 3 ESP32 en paralelo, con marca de tiempo de la Pi.
import serial, time, threading, sys, glob

DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
OUT = sys.argv[2] if len(sys.argv) > 2 else "/home/pi/capturas"
import os; os.makedirs(OUT, exist_ok=True)
DEVS = sorted(glob.glob("/dev/ttyACM*"))
print("Dispositivos:", DEVS, "| duracion:", DUR, "s | salida:", OUT)

def open_port(dev):
    s = serial.Serial()
    s.port = dev; s.baudrate = 4000000; s.timeout = 1
    s.dtr = False; s.rts = False
    s.open()
    return s

def capture(dev, idx, stop_time, counts):
    try:
        s = open_port(dev)
    except Exception as e:
        print("[rx%d] error %s: %s" % (idx, dev, e)); counts[idx] = -1; return
    fname = "%s/rx%d.csv" % (OUT, idx)
    n = 0; buf = b""
    with open(fname, "w") as f:
        while time.time() < stop_time:
            data = s.read(8192)
            if not data: continue
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                ts = time.time()
                text = line.decode("ascii", "ignore").strip()
                if text.startswith("CSI_DATA"):
                    f.write("%.6f,%s\n" % (ts, text)); n += 1
    s.close(); counts[idx] = n
    print("[rx%d] %s -> %d CSI en %s" % (idx, dev, n, fname))

stop = time.time() + DUR
counts = {}; threads = []
for i, dev in enumerate(DEVS):
    t = threading.Thread(target=capture, args=(dev, i, stop, counts)); t.start(); threads.append(t)
for t in threads: t.join()
print("RESUMEN:", dict(sorted(counts.items())), "en", DUR, "s")