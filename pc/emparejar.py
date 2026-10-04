# -*- coding: utf-8 -*-
"""
Parea cada nube de puntos de la Kinect con el CSI de los 3 ESP32 del MISMO instante.
- Kinect: timestamps en reloj PC (kinect/timestamps.csv).
- CSI:    timestamps en reloj Pi (csi/rx*.csv). Se convierten a reloj PC con el offset.
- offset (t_pi - t_pc) se lee de offset_pc_pi.txt (o pc_pi_offset.txt).

Para cada frame Kinect (PC-time T) busca, en cada RX, el CSI mas cercano a (T+offset)
dentro de una tolerancia. Emite pares nube<->CSI_rx0/rx1/rx2.

Uso:  python emparejar.py <carpeta_sesion> [tol_ms]
Salida: <sesion>/pares.csv  y resumen de cobertura.
"""
import sys, os, glob
import numpy as np

SES = sys.argv[1] if len(sys.argv) > 1 else "."
TOL = (float(sys.argv[2]) / 1000.0) if len(sys.argv) > 2 else 0.060  # 60 ms

# --- offset PC<->Pi ---
off = None
for name in ("offset_pc_pi.txt",):
    p = os.path.join(SES, name)
    if os.path.exists(p):
        off = float(open(p).read().strip()); break
if off is None:
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pc_pi_offset.txt")
    if os.path.exists(p):
        off = float(open(p).read().strip())
if off is None:
    print("No encuentro el offset PC<->Pi. Corre medir_offset.py primero."); sys.exit(1)
print("Offset (t_pi - t_pc): %.1f ms" % (off * 1000))

# --- Kinect: frame_idx, host_timestamp(PC) ---
kts_path = os.path.join(SES, "kinect", "timestamps.csv")
if not os.path.exists(kts_path):
    print("Falta", kts_path); sys.exit(1)
k_idx, k_tpc = [], []
with open(kts_path) as f:
    next(f, None)
    for line in f:
        c = line.split(",")
        if len(c) >= 2:
            try:
                k_idx.append(int(c[0])); k_tpc.append(float(c[1]))
            except: pass
k_idx = np.array(k_idx); k_tpc = np.array(k_tpc)
print("Nubes Kinect:", len(k_idx))

# --- CSI por RX: lista de (t_pc, linea_csi) ; Pi-time -> PC-time ---
csi_dir = os.path.join(SES, "csi")
rx_files = sorted(glob.glob(os.path.join(csi_dir, "rx*.csv")))
rx_names = [os.path.basename(f).split(".")[0] for f in rx_files]
rx_t = {}      # name -> np.array de tiempos PC
for f, name in zip(rx_files, rx_names):
    ts = []
    with open(f) as fh:
        for line in fh:
            c = line.split(",", 1)
            if len(c) == 2 and c[1].startswith("CSI_DATA"):
                try: ts.append(float(c[0]) - off)   # Pi -> PC
                except: pass
    rx_t[name] = np.array(sorted(ts))
print("RX encontrados:", rx_names, "| frames:", {n: len(rx_t[n]) for n in rx_names})

def nearest(arr, t):
    if len(arr) == 0: return None, 9e9
    i = np.searchsorted(arr, t)
    best = 9e9
    for j in (i-1, i):
        if 0 <= j < len(arr):
            d = abs(arr[j] - t)
            if d < best: best = d
    return best

# --- parear ---
out = os.path.join(SES, "pares.csv")
header = "kinect_frame," + ",".join("%s_err_ms" % n for n in rx_names) + ",completo\n"
n_full = 0
with open(out, "w") as fo:
    fo.write(header)
    for idx, tpc in zip(k_idx, k_tpc):
        errs = [nearest(rx_t[n], tpc) for n in rx_names]
        full = all(e <= TOL for e in errs)
        if full: n_full += 1
        fo.write("frame%03d.bin," % idx + ",".join("%.1f" % (e*1000) for e in errs) + ",%d\n" % (1 if full else 0))

print("\nPares con TODOS los RX dentro de %.0f ms: %d / %d (%.0f%%)" % (
    TOL*1000, n_full, len(k_idx), 100*n_full/max(len(k_idx),1)))
print("Guardado:", out)
print("Cada fila = una nube de puntos + el CSI mas cercano de cada RX (ese es el par para el modelo).")
