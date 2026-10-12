# -*- coding: utf-8 -*-
"""
Graficas de CSI (amplitud y fase) por receptor (rx0, rx1, rx2), comparando dos
actividades del dataset. Util para ver como cambia el CSI con la persona.

Uso:  python graficas_csi.py [ACC_A] [ACC_B]
      python graficas_csi.py A01 A02      # habitacion vs estatica (por defecto)
"""
import os, sys, glob
import numpy as np, scipy.io as scio
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("CSI2PC_DATA", os.path.join(HERE, "..", "mmfi_dataset"))
OUT  = os.path.join(HERE, "resultados")
os.makedirs(OUT, exist_ok=True)
ROOT = os.path.join(DATA, "E01", "S01")

ACC_A = sys.argv[1] if len(sys.argv) > 1 else "A01"
ACC_B = sys.argv[2] if len(sys.argv) > 2 else "A02"
NOMBRE = {"A01": "habitacion", "A02": "estatica", "A03": "sentadilla",
          "A04": "caminar", "A05": "torso", "A06": "actividad6"}


def carga(acc):
    A, P = [], []
    for m in sorted(glob.glob(os.path.join(ROOT, acc, "wifi-csi", "*.mat"))):
        d = scio.loadmat(m); amp = d["CSIamp"].astype(float); pha = d["CSIphase"].astype(float)
        amp[np.isinf(amp)] = np.nan; pha[np.isinf(pha)] = np.nan
        A.append(np.nanmean(amp, axis=2)); P.append(np.nanmean(pha, axis=2))  # (3,114)
    return np.array(A), np.array(P)


Aa, Pa = carga(ACC_A)
Ab, Pb = carga(ACC_B)
la, lb = NOMBRE.get(ACC_A, ACC_A), NOMBRE.get(ACC_B, ACC_B)

fig, ax = plt.subplots(2, 3, figsize=(15, 7))
for rx in range(3):
    ax[0, rx].plot(np.nanmean(Aa[:, rx], 0), label=la, color="#1f6fe0")
    ax[0, rx].plot(np.nanmean(Ab[:, rx], 0), label=lb, color="#e02020")
    ax[0, rx].set_title("rx%d - AMPLITUD" % rx); ax[0, rx].grid(alpha=.3); ax[0, rx].set_xlabel("subportadora")
    ax[1, rx].plot(np.nanmean(Pa[:, rx], 0), label=la, color="#1f6fe0")
    ax[1, rx].plot(np.nanmean(Pb[:, rx], 0), label=lb, color="#e02020")
    ax[1, rx].set_title("rx%d - FASE" % rx); ax[1, rx].grid(alpha=.3); ax[1, rx].set_xlabel("subportadora")
ax[0, 0].set_ylabel("amplitud media"); ax[1, 0].set_ylabel("fase media (rad)"); ax[0, 0].legend()
plt.suptitle("CSI por receptor: %s (azul) vs %s (rojo)" % (la.upper(), lb.upper()))
plt.tight_layout()
dst = os.path.join(OUT, "csi_%s_vs_%s.png" % (la, lb))
plt.savefig(dst, dpi=120)
print("OK ->", dst, "| %s %d frames, %s %d frames" % (la, len(Aa), lb, len(Ab)))
