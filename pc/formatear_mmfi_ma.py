# -*- coding: utf-8 -*-
"""
Formatea a MM-Fi aplicando SOLO la media movil (sliding window) como Maata.
Se promedia el CSI COMPLEJO (I/Q) con ventana deslizante -> de ahi se derivan
amplitud y fase (ambas suavizadas correctamente, sin el error de promediar fase
envuelta). NADA de Hampel/unwrap/STO. La normalizacion (min-max amp + mean/std)
se hace en el dataloader de entrenamiento, igual que Maata.

Uso:  python formatear_mmfi_ma.py <sesion> [E] [S] [A] [ventana]
"""
import sys, os, glob, re, shutil
import numpy as np
import scipy.io as scio

SES = sys.argv[1]
E   = sys.argv[2] if len(sys.argv) > 2 else "E01"
S   = sys.argv[3] if len(sys.argv) > 3 else "S01"
A   = sys.argv[4] if len(sys.argv) > 4 else "A01"
MA_WIN = int(sys.argv[5]) if len(sys.argv) > 5 else 5   # ventana de la media movil
OUTROOT = os.path.join(os.path.dirname(SES.rstrip("\\/")), "mmfi_dataset")
DST = os.path.join(OUTROOT, E, S, A)
os.makedirs(os.path.join(DST, "wifi-csi"), exist_ok=True)
os.makedirs(os.path.join(DST, "lidar"), exist_ok=True)

T_STEPS = 10
N_SUB   = 114
RAW_LEN = 384  # solo paquetes HT40 (192 complejos); len=256 es HT20 -> se descarta
MAX_CSI_CLOUD_DT = 0.15  # s: distancia maxima nube <-> centro de la ventana CSI
DATA_RE = re.compile(r'\[([-\d,]+)\]')

def read_offset():
    for p in (os.path.join(SES, "offset_pc_pi.txt"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "pc_pi_offset.txt")):
        if os.path.exists(p):
            return float(open(p).read().strip())
    raise SystemExit("Falta offset PC<->Pi.")
OFF = read_offset()

def ht40_complex(vals):
    """Devuelve el CSI COMPLEJO de las 114 subportadoras HT40.

    De los 192 complejos del paquete, el bloque HT-LTF son 66..122 y 134..190
    (57+57); LLTF (6..58) y los huecos de guarda/DC quedan fuera.
    """
    if len(vals) != RAW_LEN:
        return None                          # HT20 (len=256) u otro formato
    a = np.array(vals, dtype=np.float64)
    Q = a[0::2]; I = a[1::2]
    comp = I + 1j * Q
    comp = np.concatenate([comp[66:123], comp[134:191]])
    if comp.shape[0] != N_SUB:
        return None
    return comp

def moving_average_complex(X, win):
    """Media movil centrada sobre el eje tiempo (axis=0), parte real e imaginaria."""
    if win <= 1:
        return X
    kernel = np.ones(win) / win
    re = np.apply_along_axis(lambda c: np.convolve(c, kernel, mode='same'), 0, X.real)
    im = np.apply_along_axis(lambda c: np.convolve(c, kernel, mode='same'), 0, X.imag)
    return re + 1j * im

def load_rx(path):
    ts, comps = [], []
    n_tot = n_drop = 0
    with open(path) as f:
        for line in f:
            c = line.split(",", 1)
            if len(c) != 2 or not c[1].startswith("CSI_DATA"):
                continue
            m = DATA_RE.search(c[1])
            if not m: continue
            try:
                vals = [int(x) for x in m.group(1).split(",") if x != ""]
            except ValueError:
                continue   # paquete corrupto (glitch del serial, p.ej. "4-38"): se salta
            n_tot += 1
            comp = ht40_complex(vals)
            if comp is None:
                n_drop += 1; continue
            ts.append(float(c[0]) - OFF); comps.append(comp)
    print("  %s: %d CSI, %d HT40 (len=384), %d descartados (no HT40)"
          % (os.path.basename(path), n_tot, n_tot - n_drop, n_drop))
    if not ts:
        return np.array([]), None, None
    o = np.argsort(ts)
    ts = np.array(ts)[o]; comp = np.array(comps)[o]      # [N,114] complejo
    comp = moving_average_complex(comp, MA_WIN)          # <-- MEDIA MOVIL (Maata)
    amp = np.abs(comp); pha = np.angle(comp)             # amplitud y fase del complejo suavizado
    return ts, amp, pha

rx_files = sorted(glob.glob(os.path.join(SES, "csi", "rx*.csv")))[:3]
print("Aplicando media movil (ventana=%d) sobre CSI complejo..." % MA_WIN)
rx = [load_rx(f) for f in rx_files]
print("RX:", [os.path.basename(f) for f in rx_files], "| frames:", [len(r[0]) for r in rx])
if len(rx) < 3 or any(len(r[0]) < T_STEPS for r in rx):
    print("Hacen falta 3 RX con suficientes muestras."); sys.exit(1)

kts = {}
with open(os.path.join(SES, "kinect", "timestamps.csv")) as f:
    next(f, None)
    for line in f:
        c = line.split(",")
        if len(c) >= 2:
            try: kts[int(c[0])] = float(c[1])
            except: pass

def window10(ts_arr, t):
    i = np.searchsorted(ts_arr, t)
    lo = max(0, i - T_STEPS // 2); hi = lo + T_STEPS
    if hi > len(ts_arr): hi = len(ts_arr); lo = hi - T_STEPS
    return np.arange(lo, hi)

def window_dt(ts_arr, w, t):
    """Distancia (s) de t al centro de la ventana (el borde dista ~0.05 s por
    construccion a ~95 Hz, asi que medir el borde descartaria casi todo)."""
    return abs(float(np.median(ts_arr[w])) - t)

n_ok = 0
n_lejos = 0
for idx in sorted(kts):
    tpc = kts[idx]
    binsrc = os.path.join(SES, "kinect", "frame%03d.bin" % idx)
    if not os.path.exists(binsrc): continue
    amp3 = np.zeros((3, N_SUB, T_STEPS)); pha3 = np.zeros((3, N_SUB, T_STEPS))
    ok = True
    for r in range(3):
        ts_arr, amps, phas = rx[r]
        w = window10(ts_arr, tpc)
        if len(w) < T_STEPS: ok = False; break
        if window_dt(ts_arr, w, tpc) > MAX_CSI_CLOUD_DT:
            ok = False; n_lejos += 1; break    # hueco en el CSI
        amp3[r] = amps[w].T; pha3[r] = phas[w].T
    if not ok: continue
    n_ok += 1
    scio.savemat(os.path.join(DST, "wifi-csi", "frame%03d.mat" % n_ok),
                 {"CSIamp": amp3, "CSIphase": pha3})
    shutil.copy(binsrc, os.path.join(DST, "lidar", "frame%03d.bin" % n_ok))

print("Frames MM-Fi (con media movil) generados: %d" % n_ok)
print("Frames descartados por desfase nube<->CSI (> %.3f s): %d" % (MAX_CSI_CLOUD_DT, n_lejos))
print("Salida:", DST)
print(">> data_root:", OUTROOT)
