# -*- coding: utf-8 -*-
"""
Convierte una sesion capturada (Kinect + CSI 3 RX) a la estructura MM-Fi que
lee el modelo de Maata (csi2pointcloud).

Entrada  (carpeta de sesion):
    kinect/frame###.bin        nubes float64 (N,3)  [reloj PC]
    kinect/timestamps.csv      frame_idx, host_timestamp(PC), ...
    csi/rx0.csv rx1.csv rx2.csv  CSI con seq           [reloj Pi]
    offset_pc_pi.txt           (t_pi - t_pc)  [o se toma de capturas_csi]

Salida (estructura MM-Fi):
    <out>/E01/S01/A01/
        wifi-csi/frame###.mat   CSIamp[3,114,10], CSIphase[3,114,10]
        lidar/frame###.bin      la nube (copiada)

Para cada nube (10 Hz) toma las 10 muestras CSI por RX mas cercanas en el tiempo
(ventana centrada en el instante de la nube) y extrae las 114 subportadoras HT40.

Uso:  python formatear_mmfi.py <sesion> [E] [S] [A]
"""
import sys, os, glob, re, shutil
import numpy as np
import scipy.io as scio

SES = sys.argv[1]
E   = sys.argv[2] if len(sys.argv) > 2 else "E01"
S   = sys.argv[3] if len(sys.argv) > 3 else "S01"
A   = sys.argv[4] if len(sys.argv) > 4 else "A01"
OUTROOT = os.path.join(os.path.dirname(SES.rstrip("\\/")), "mmfi_dataset")
DST = os.path.join(OUTROOT, E, S, A)
os.makedirs(os.path.join(DST, "wifi-csi"), exist_ok=True)
os.makedirs(os.path.join(DST, "lidar"), exist_ok=True)

T_STEPS = 10   # muestras temporales por frame (MM-Fi usa 10)
N_SUB   = 114  # subportadoras HT40
DATA_RE = re.compile(r'\[([-\d,]+)\]')

# --- offset PC<->Pi ---
def read_offset():
    for p in (os.path.join(SES, "offset_pc_pi.txt"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "pc_pi_offset.txt")):
        if os.path.exists(p):
            return float(open(p).read().strip())
    raise SystemExit("Falta offset PC<->Pi (corre medir_offset.py).")
OFF = read_offset()

def ht40_amp_phase(vals):
    """De un array de 612 (o 380) valores I/Q -> amplitud y fase de 114 subp HT40."""
    a = np.array(vals, dtype=np.float64)
    Q = a[0::2]; I = a[1::2]                 # par=Q(imag), impar=I(real)
    amp = np.sqrt(I**2 + Q**2)
    pha = np.arctan2(Q, I)
    # bloque HT-LTF = 114 subportadoras (saltando hueco DC)
    if amp.shape[0] >= 184:
        amp = np.concatenate([amp[66:123], amp[127:184]])
        pha = np.concatenate([pha[66:123], pha[127:184]])
    else:  # len=380 (190 valores): HT-LTF empieza antes; fallback: ultimos 114
        amp = amp[-N_SUB:]; pha = pha[-N_SUB:]
    if amp.shape[0] != N_SUB:
        return None, None
    return amp, pha

def load_rx(path):
    """Devuelve (ts_pc[], amp[Nx114], pha[Nx114]) de un rxN.csv."""
    ts, amps, phas = [], [], []
    with open(path) as f:
        for line in f:
            c = line.split(",", 1)
            if len(c) != 2 or not c[1].startswith("CSI_DATA"):
                continue
            m = DATA_RE.search(c[1])
            if not m:
                continue
            vals = [int(x) for x in m.group(1).split(",") if x != ""]
            amp, pha = ht40_amp_phase(vals)
            if amp is None:
                continue
            ts.append(float(c[0]) - OFF)     # Pi -> PC
            amps.append(amp); phas.append(pha)
    if not ts:
        return np.array([]), None, None
    o = np.argsort(ts)
    return np.array(ts)[o], np.array(amps)[o], np.array(phas)[o]

# --- cargar los 3 RX ---
rx_files = sorted(glob.glob(os.path.join(SES, "csi", "rx*.csv")))[:3]
rx = [load_rx(f) for f in rx_files]
print("RX:", [os.path.basename(f) for f in rx_files], "| frames:", [len(r[0]) for r in rx])
if len(rx) < 3 or any(len(r[0]) < T_STEPS for r in rx):
    print("Hacen falta 3 RX con suficientes muestras."); sys.exit(1)

# --- nubes Kinect + timestamps ---
kts = {}
with open(os.path.join(SES, "kinect", "timestamps.csv")) as f:
    next(f, None)
    for line in f:
        c = line.split(",")
        if len(c) >= 2:
            try: kts[int(c[0])] = float(c[1])
            except: pass

def window10(ts_arr, t):
    """Indices de las 10 muestras mas cercanas a t (centradas)."""
    i = np.searchsorted(ts_arr, t)
    lo = max(0, i - T_STEPS // 2)
    hi = lo + T_STEPS
    if hi > len(ts_arr):
        hi = len(ts_arr); lo = hi - T_STEPS
    return np.arange(lo, hi)

n_ok = 0
for idx in sorted(kts):
    tpc = kts[idx]
    binsrc = os.path.join(SES, "kinect", "frame%03d.bin" % idx)
    if not os.path.exists(binsrc):
        continue
    amp3 = np.zeros((3, N_SUB, T_STEPS), dtype=np.float64)
    pha3 = np.zeros((3, N_SUB, T_STEPS), dtype=np.float64)
    ok = True
    for r in range(3):
        ts_arr, amps, phas = rx[r]
        w = window10(ts_arr, tpc)
        if len(w) < T_STEPS:
            ok = False; break
        amp3[r] = amps[w].T    # [114, 10]
        pha3[r] = phas[w].T
    if not ok:
        continue
    n_ok += 1
    scio.savemat(os.path.join(DST, "wifi-csi", "frame%03d.mat" % n_ok),
                 {"CSIamp": amp3, "CSIphase": pha3})
    shutil.copy(binsrc, os.path.join(DST, "lidar", "frame%03d.bin" % n_ok))

print("Frames MM-Fi generados: %d" % n_ok)
print("Salida:", DST)
print("  wifi-csi/frame###.mat  (CSIamp[3,114,10], CSIphase[3,114,10])")
print("  lidar/frame###.bin     (nube)")
print(">> data_root para el modelo:", OUTROOT)
