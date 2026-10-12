# -*- coding: utf-8 -*-
"""
Espectro CSI como mapa de calor (subportadora x tiempo) por receptor y actividad.
Se ve como evoluciona el CSI en el tiempo: en movimiento aparecen franjas/variacion,
en estatico/habitacion es mas plano. Uso: python espectro_csi.py [n_frames]
"""
import os, sys, glob
import numpy as np, scipy.io as scio
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("CSI2PC_DATA", os.path.join(HERE, "..", "mmfi_dataset"))
OUT  = os.path.join(HERE, "resultados"); os.makedirs(OUT, exist_ok=True)
ROOT = os.path.join(DATA, "E01", "S01")
NF = int(sys.argv[1]) if len(sys.argv) > 1 else 250   # frames a mostrar

ACTS = [("A01", "habitacion"), ("A02", "estatica"), ("A03", "sentadilla"),
        ("A04", "caminar"), ("A05", "torso")]
ACTS = [a for a in ACTS if os.path.isdir(os.path.join(ROOT, a[0]))]


def amp_cube(acc, nf):
    mats = sorted(glob.glob(os.path.join(ROOT, acc, "wifi-csi", "*.mat")))[:nf]
    M = []
    for m in mats:
        d = scio.loadmat(m)["CSIamp"].astype(float)  # (3,114,10)
        d[np.isinf(d)] = np.nan
        M.append(np.nanmean(d, axis=2))              # (3,114) media de la ventana
    return np.array(M)                                # (N,3,114)


fig, ax = plt.subplots(len(ACTS), 3, figsize=(14, 2.4 * len(ACTS)))
if len(ACTS) == 1: ax = ax[None, :]
for i, (acc, nom) in enumerate(ACTS):
    C = amp_cube(acc, NF)   # (N,3,114)
    for rx in range(3):
        im = ax[i, rx].imshow(C[:, rx].T, aspect="auto", origin="lower", cmap="viridis")
        if i == 0: ax[i, rx].set_title("rx%d" % rx, fontsize=11)
        if rx == 0: ax[i, rx].set_ylabel("%s\nsubportadora" % nom, fontsize=9)
        if i == len(ACTS) - 1: ax[i, rx].set_xlabel("frame (tiempo)", fontsize=9)
plt.suptitle("Espectro CSI (subportadora x tiempo) - amplitud, por receptor y actividad")
plt.tight_layout()
dst = os.path.join(OUT, "espectro_csi.png")
plt.savefig(dst, dpi=120)
print("OK ->", dst)
