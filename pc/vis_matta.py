# -*- coding: utf-8 -*-
"""
vis_matta.py  -  Visualiza GT (Kinect) vs Predicho (CSI->IA) con los COLORES DE MAATA:
colormap 'viridis' coloreado por distancia al sensor (igual que scripts/test_model.py
del repo oficial csi2pointcloud). Orientacion de pie correcta.

Uso:  python vis_matta.py [accion A0X] [frame_en_esa_accion]
      python vis_matta.py A03 10
Si no se pasa accion, usa un frame del TEST (split.json).
"""
import os, sys, glob, json
import numpy as np, scipy.io as scio, torch
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("CSI2PC_REPO", os.path.join(_HERE, "..", "csi2pointcloud"))
ROOT = os.environ.get("CSI2PC_DATA", os.path.join(_HERE, "..", "mmfi_dataset"))
OUT  = os.environ.get("CSI2PC_OUT",  os.path.join(_HERE, "resultados"))
CKPT = os.path.join(OUT, "modelo", "csi2pc_v2.pth")
sys.path.append(REPO)
from src.csi2pointcloud.csi2pointcloud_arch01 import CSI2PointCloudModel

# elegir frame
mats_all = sorted(glob.glob(os.path.join(ROOT, "**", "wifi-csi", "*.mat"), recursive=True))
mats_all = [m for m in mats_all if os.path.exists(m.replace("wifi-csi", "lidar").replace(".mat", ".bin"))]
if len(sys.argv) >= 3:
    acc, fr = sys.argv[1].upper(), int(sys.argv[2])
    cand = [m for m in mats_all if ("%s%s" % (os.sep, acc)) in m]
    mat = cand[fr - 1]
else:
    sp = json.load(open(os.path.join(OUT, "split.json")))
    mat = mats_all[sp["test"][len(sp["test"]) // 2]]
binf = mat.replace("wifi-csi", "lidar").replace(".mat", ".bin")
etiqueta = os.path.basename(os.path.dirname(os.path.dirname(mat)))

# CSI normalizado (igual que train)
m = scio.loadmat(mat)
amp = m["CSIamp"].astype(np.float64); pha = m["CSIphase"].astype(np.float64)
amp[np.isinf(amp)] = np.nan; pha[np.isinf(pha)] = np.nan
if np.any(np.isnan(amp)): amp[np.isnan(amp)] = np.nanmean(amp)
if np.any(np.isnan(pha)): pha[np.isnan(pha)] = np.nanmean(pha)
amp = (amp - np.nanmin(amp)) / (np.nanmax(amp) - np.nanmin(amp) + 1e-9)
csi = np.stack([amp, pha], axis=2).astype(np.float32)
x = torch.from_numpy(csi); x = (x - x.mean()) / (x.std() + 1e-9)

gt = np.frombuffer(open(binf, "rb").read(), dtype=np.float64).reshape(-1, 3).astype(np.float32)

model = CSI2PointCloudModel(256, 4, 3, 3, 1200, 3, 114, 10)
model.load_state_dict(torch.load(CKPT)["model_state_dict"]); model.eval()
with torch.no_grad(): pred, _ = model(x.unsqueeze(0))
pred = pred.squeeze(0).numpy()


def plot_maata(ax, P, titulo):
    """Colores de Maata: viridis por distancia al sensor. Orientacion de pie (X, Z, -Y)."""
    h, prof, alt = P[:, 0], P[:, 2], -P[:, 1]
    dist = np.linalg.norm(P, axis=1)
    sc = ax.scatter(h, prof, alt, c=dist, cmap="viridis", s=7, alpha=0.9)
    ax.set_title(titulo, fontsize=14)
    ax.set_xlabel("X"); ax.set_ylabel("Z"); ax.set_zlabel("altura (-Y)")
    ax.view_init(elev=12, azim=-75)
    return sc


fig = plt.figure(figsize=(13, 6))
plot_maata(fig.add_subplot(1, 2, 1, projection="3d"), gt,   "Ground-truth (Kinect)  [%s]" % etiqueta)
plot_maata(fig.add_subplot(1, 2, 2, projection="3d"), pred, "Predicho (CSI -> IA)")
plt.suptitle("Generacion de nube de puntos  -  colores de Maata (viridis por distancia)")
plt.tight_layout()
dst = os.path.join(OUT, "maata_gt_vs_pred_%s.png" % etiqueta)
plt.savefig(dst, dpi=130, bbox_inches="tight")
print("OK ->", dst, "| accion", etiqueta, "| gt", gt.shape, "pred", pred.shape)
