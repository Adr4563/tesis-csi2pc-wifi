# -*- coding: utf-8 -*-
"""
Formatea a MM-Fi aplicando SOLO dos filtros:
  - AMPLITUD: filtro de Hampel (quita outliers por mediana/MAD, por subportadora
    a lo largo del tiempo).
  - FASE: saneamiento STO (Sampling Time Offset): por paquete se quita el desfase
    lineal a lo largo de las subportadoras (se ajusta una recta a*k+b y se resta).
No se usa media movil ni DWT. La normalizacion (min-max amp + mean/std) se hace
en el dataloader de entrenamiento, igual que Maata.

Uso:  python formatear_mmfi_ma.py <sesion> [E] [S] [A] [ventana_hampel]
"""
import sys, os, glob, re, shutil
import numpy as np
import pandas as pd
import scipy.io as scio

SES = sys.argv[1]
E   = sys.argv[2] if len(sys.argv) > 2 else "E01"
S   = sys.argv[3] if len(sys.argv) > 3 else "S01"
A   = sys.argv[4] if len(sys.argv) > 4 else "A01"
HAMP_WIN = int(sys.argv[5]) if len(sys.argv) > 5 else 7   # ventana del filtro de Hampel
HAMP_SIG = 3.0                                            # umbral (n * sigma) del Hampel
# El dataset va SIEMPRE a <repo>/mmfi_dataset (pc/ esta en la raiz del repo),
# sin importar donde este la sesion de captura.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTROOT = os.path.join(REPO, "mmfi_dataset")
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
    """Convierte los 384 enteros crudos del ESP32 en las 114 subportadoras
    complejas (I/Q -> numero complejo).

    El ESP32 entrega los valores intercalados como [Q0, I0, Q1, I1, ...]:
    las posiciones pares son la parte imaginaria (Q) y las impares la real (I).
    De las 192 subportadoras del paquete solo son utiles las del bloque HT-LTF
    (66..122 y 134..190 = 57+57 = 114); LLTF y los huecos de guarda/DC se quitan.
    """
    if len(vals) != RAW_LEN:
        return None                          # HT20 (len=256) u otro formato -> se descarta
    a = np.array(vals, dtype=np.float64)
    Q = a[0::2]                               # parte imaginaria (posiciones pares)
    I = a[1::2]                               # parte real      (posiciones impares)
    comp = I + 1j * Q                         # CSI complejo:   z = I + jQ
    comp = np.concatenate([comp[66:123], comp[134:191]])   # solo las 114 utiles (HT-LTF)
    if comp.shape[0] != N_SUB:
        return None
    return comp

def hampel_amp(amp, win, n_sig):
    """Filtro de Hampel sobre la amplitud, por subportadora a lo largo del tiempo.

    Para cada subportadora (columna) se calcula, con una ventana movil de 'win':
        mediana  = mediana local
        MAD      = mediana de |valor - mediana local|   (desviacion absoluta mediana)
        sigma    = 1.4826 * MAD                          (equivalente a la desv. tipica)
    Si un valor se aleja mas de n_sig*sigma de la mediana, se considera outlier
    (un pico raro) y se reemplaza por la mediana local.
    """
    amp = pd.DataFrame(amp)                   # filas = tiempo, columnas = subportadoras
    mediana = amp.rolling(win, center=True, min_periods=1).median()
    desv = (amp - mediana).abs()
    mad = 1.4826 * desv.rolling(win, center=True, min_periods=1).median()
    es_outlier = desv > n_sig * mad           # True donde hay un pico anomalo
    limpio = amp.mask(es_outlier, mediana)    # reemplaza esos picos por la mediana local
    return limpio.to_numpy()

def sto_phase(pha):
    """Saneamiento STO (Sampling Time Offset) de la fase, un paquete a la vez.

    A cada paquete se le resta la recta  a*k + b  a lo largo de las subportadoras k:
        a = (fase_ultima - fase_primera) / (k_ultima - k_primera)   # pendiente (STO)
        b = promedio de la fase                                     # offset
        fase_saneada = fase_desenvuelta - (a*k + b)
    Asi se quita el desfase lineal introducido por el desfase de muestreo.
    """
    k = np.arange(pha.shape[1], dtype=np.float64)   # indice de subportadora: 0,1,...,113
    salida = np.zeros_like(pha)
    for i in range(pha.shape[0]):                   # recorre cada paquete
        u = np.unwrap(pha[i])                       # desenvuelve la fase (quita saltos de 2*pi)
        a = (u[-1] - u[0]) / (k[-1] - k[0])         # pendiente de la recta
        b = u.mean()                                # offset de la recta
        salida[i] = u - (a * k + b)                 # resta la recta
    return salida

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
    amp = np.abs(comp)                                   # amplitud = |z| = sqrt(I^2 + Q^2)
    pha = np.angle(comp)                                 # fase     = atan2(Q, I)
    amp = hampel_amp(amp, HAMP_WIN, HAMP_SIG)            # <-- HAMPEL en amplitud
    pha = sto_phase(pha)                                 # <-- STO en fase
    return ts, amp, pha

rx_files = sorted(glob.glob(os.path.join(SES, "csi", "rx*.csv")))[:3]
print("Aplicando Hampel (ventana=%d, %.1f-sigma) en amplitud y STO en fase..." % (HAMP_WIN, HAMP_SIG))
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

print("Frames MM-Fi (Hampel + STO) generados: %d" % n_ok)
print("Frames descartados por desfase nube<->CSI (> %.3f s): %d" % (MAX_CSI_CLOUD_DT, n_lejos))
print("Salida:", DST)
print(">> data_root:", OUTROOT)
