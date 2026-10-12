# -*- coding: utf-8 -*-
"""
Espectro CSI mostrando el PREPROCESAMIENTO paso a paso (tecnicas de Maata/MM-Fi):
  1. Extraccion HT40 (114 subp)      -> ya viene en el .mat
  2. Media movil sobre CSI complejo  -> ya viene en el .mat (amplitud/fase suavizadas)
  3. Amplitud = |CSI|
  4. Normalizacion min-max [0,1]
  5. Estandarizacion (x-mean)/std
Genera un mapa de calor (subportadora x tiempo) para una actividad, en 3 etapas:
  CRUDO (amplitud) | NORMALIZADO [0,1] | ESTANDARIZADO
Uso:  python espectro_preproc.py [ACC] [rx] [n_frames]
"""
import os, sys, glob
import numpy as np, scipy.io as scio
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("CSI2PC_DATA", os.path.join(HERE, "..", "mmfi_dataset"))
OUT  = os.path.join(HERE, "resultados"); os.makedirs(OUT, exist_ok=True)
ACC = sys.argv[1] if len(sys.argv) > 1 else "A03"
RX  = int(sys.argv[2]) if len(sys.argv) > 2 else 0
NF  = int(sys.argv[3]) if len(sys.argv) > 3 else 250
NOM = {"A01": "habitacion", "A02": "estatica", "A03": "sentadilla", "A04": "caminar", "A05": "torso"}

mats = sorted(glob.glob(os.path.join(DATA, "E01", "S01", ACC, "wifi-csi", "*.mat")))[:NF]
amp = []
for m in mats:
    d = scio.loadmat(m)["CSIamp"].astype(float)   # (3,114,10) ya con media movil (paso 1-2)
    d[np.isinf(d)] = np.nan
    amp.append(np.nanmean(d[RX], axis=1))          # (114,) media de la ventana temporal
A = np.array(amp)                                   # (N,114) amplitud "cruda" (post media movil)

# paso 4: normalizacion min-max [0,1] por frame (como Maata, con nan->nanmin)
def minmax(x):
    mn, mx = np.nanmin(x), np.nanmax(x)
    return (x - mn) / (mx - mn + 1e-9)
An = np.array([minmax(r) for r in A])

# paso 5: estandarizacion (x-mean)/std por frame
As = np.array([(r - np.nanmean(r)) / (np.nanstd(r) + 1e-9) for r in An])

fig, ax = plt.subplots(1, 3, figsize=(16, 4.5))
for a, M, t in [(ax[0], A, "1-3) Amplitud (HT40 + media movil)"),
                (ax[1], An, "4) Normalizado min-max [0,1]"),
                (ax[2], As, "5) Estandarizado (x-mean)/std")]:
    im = a.imshow(M.T, aspect="auto", origin="lower", cmap="viridis")
    a.set_title(t, fontsize=11); a.set_xlabel("frame (tiempo)"); a.set_ylabel("subportadora")
    plt.colorbar(im, ax=a, fraction=0.046)
plt.suptitle("Preprocesamiento del CSI - %s (rx%d)  [tecnicas de Maata/MM-Fi]" % (NOM.get(ACC, ACC), RX))
plt.tight_layout()
dst = os.path.join(OUT, "espectro_preproc_%s_rx%d.png" % (NOM.get(ACC, ACC), RX))
plt.savefig(dst, dpi=120)
print("OK ->", dst)
