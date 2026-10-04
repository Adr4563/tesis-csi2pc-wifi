# -*- coding: utf-8 -*-
"""GIF ligero: GT (azul) vs Predicho (rojo) recorriendo frames. Vista frontal correcta.
Uso: python video_pred.py"""
import os, sys, glob, io
import numpy as np, scipy.io as scio, torch
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

REPO = r"C:\Users\user\Desktop\Carpeta_Trabajo\csi2pointcloud"
ROOT = r"C:\Users\user\Desktop\Carpeta_Trabajo\capturas_sync\mmfi_dataset\E01\S01\A01"
_OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados")
CKPT = os.path.join(_OUTDIR, "modelo", "csi2pc_v2.pth")
OUT  = os.path.join(_OUTDIR, "gt_vs_pred.gif")
sys.path.append(REPO)
from src.csi2pointcloud.csi2pointcloud_arch01 import CSI2PointCloudModel

mats = sorted(glob.glob(os.path.join(ROOT, "wifi-csi", "*.mat")))
bins = sorted(glob.glob(os.path.join(ROOT, "lidar", "*.bin")))
STEP = 3                      # 1 de cada 3 frames -> ligero
idxs = list(range(0, len(mats), STEP))

model = CSI2PointCloudModel(256, 4, 3, 3, 1200, 3, 114, 10)
model.load_state_dict(torch.load(CKPT)["model_state_dict"]); model.eval()

def csi_tensor(mat):
    m = scio.loadmat(mat)
    amp = m["CSIamp"].astype(np.float64); pha = m["CSIphase"].astype(np.float64)
    amp[np.isinf(amp)] = np.nan; pha[np.isinf(pha)] = np.nan
    if np.any(np.isnan(amp)): amp[np.isnan(amp)] = np.nanmean(amp)
    if np.any(np.isnan(pha)): pha[np.isnan(pha)] = np.nanmean(pha)
    amp = (amp - np.nanmin(amp)) / (np.nanmax(amp) - np.nanmin(amp) + 1e-9)
    csi = np.stack([amp, pha], axis=2).astype(np.float32)
    x = torch.from_numpy(csi); return (x - x.mean()) / (x.std() + 1e-9)

def frontal(Q):
    h = Q[:, 0] - Q[:, 0].mean(); v = -Q[:, 1] - (-Q[:, 1]).mean(); return h, v

frames = []
for k, i in enumerate(idxs):
    gt = np.frombuffer(open(bins[i], "rb").read(), dtype=np.float64).reshape(-1, 3).astype(np.float32)
    x = csi_tensor(mats[i])
    with torch.no_grad():
        pred, _ = model(x.unsqueeze(0))
    pred = pred.squeeze(0).numpy()

    fig, axes = plt.subplots(1, 2, figsize=(6, 3.3), dpi=80)
    for ax, Q, ti in [(axes[0], gt, "GROUND-TRUTH (Kinect)"),
                      (axes[1], pred, "PREDICHO (CSI->IA)")]:
        h, v = frontal(Q)
        dist = np.linalg.norm(Q, axis=1)          # colores de Maata: viridis por distancia
        ax.scatter(h, v, s=2, c=dist, cmap="viridis")
        ax.set_title(ti, fontsize=8); ax.set_aspect("equal")
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values(): s.set_visible(False)
    fig.suptitle("frame %d/%d" % (i + 1, len(mats)), fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO(); fig.savefig(buf, format="png"); plt.close(fig)
    buf.seek(0); frames.append(Image.open(buf).convert("P", palette=Image.ADAPTIVE))
    if k % 10 == 0: print("render %d/%d" % (k, len(idxs)), flush=True)

frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=120, loop=0, optimize=True)
print("OK ->", OUT, "| %d frames | %.1f KB" % (len(frames), os.path.getsize(OUT) / 1024))
