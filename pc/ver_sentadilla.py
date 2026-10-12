# -*- coding: utf-8 -*-
"""
Resultados del modelo de sentadillas (A03): Chamfer sobre val + GIF animado
GT vs Predicho recorriendo frames consecutivos (se VE el movimiento de la sentadilla).
Colores de Maata (viridis por distancia). Uso: python ver_sentadilla.py
"""
import os, sys, glob, io, json
import numpy as np, scipy.io as scio, torch
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
import open3d as o3d

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..", "tesis", "modelo")
DATA = os.environ.get("CSI2PC_DATA", r"C:\Users\user\Desktop\Carpeta_Trabajo\capturas_sync\mmfi_dataset")
OUT  = os.path.join(HERE, "resultados_sentadilla")
sys.path.insert(0, REPO)
from csi2pointcloud.csi2pointcloud_arch01 import CSI2PointCloudModel

ckpt = os.path.join(OUT, "modelo", "csi2pc_sentadilla_best.pth")
model = CSI2PointCloudModel(256, 4, 3, 3, 1200, 3, 114, 10)
model.load_state_dict(torch.load(ckpt, map_location="cpu")["model_state_dict"]); model.eval()

mats = sorted(glob.glob(os.path.join(DATA, "**", "A03", "wifi-csi", "*.mat"), recursive=True))
bins = [m.replace("wifi-csi", "lidar").replace(".mat", ".bin") for m in mats]


def csi_tensor(mat):
    m = scio.loadmat(mat)
    amp = m["CSIamp"].astype(np.float64); pha = m["CSIphase"].astype(np.float64)
    amp[np.isinf(amp)] = np.nan; pha[np.isinf(pha)] = np.nan
    if np.any(np.isnan(amp)): amp[np.isnan(amp)] = np.nanmean(amp)
    if np.any(np.isnan(pha)): pha[np.isnan(pha)] = np.nanmean(pha)
    amp = (amp - np.nanmin(amp)) / (np.nanmax(amp) - np.nanmin(amp) + 1e-9)
    csi = np.stack([amp, pha], axis=2).astype(np.float32)
    x = torch.from_numpy(csi); return (x - x.mean()) / (x.std() + 1e-9)


def nn(A, B):
    kdt = o3d.geometry.KDTreeFlann(o3d.geometry.PointCloud(o3d.utility.Vector3dVector(B)))
    return np.array([np.sqrt(kdt.search_knn_vector_3d(p, 1)[2][0]) for p in A])


# --- Chamfer sobre el val (del split de entrenamiento) ---
val = json.load(open(os.path.join(OUT, "split.json")))["val"]
chamfs = []
for i in val:
    gt = np.frombuffer(open(bins[i], "rb").read(), dtype=np.float64).reshape(-1, 3)
    with torch.no_grad():
        pred = model(csi_tensor(mats[i]).unsqueeze(0))[0].squeeze(0).numpy().astype(np.float64)
    pred_m = pred * gt.std() + gt.mean()
    chamfs.append(nn(pred_m, gt).mean() + nn(gt, pred_m).mean())
print("Chamfer medio en val (sentadillas): %.4f m" % np.mean(chamfs))

# --- GIF: frames consecutivos (se ve el movimiento) ---
def frontal(Q): return Q[:, 0] - Q[:, 0].mean(), (-Q[:, 1]) - (-Q[:, 1]).mean()

frames_gif = []
sel = range(0, min(len(mats), 180), 2)   # frames consecutivos (una corrida de sentadillas)
for i in sel:
    gt = np.frombuffer(open(bins[i], "rb").read(), dtype=np.float64).reshape(-1, 3).astype(np.float32)
    g = (gt - gt.mean()) / (gt.std() + 1e-9)
    with torch.no_grad():
        pred = model(csi_tensor(mats[i]).unsqueeze(0))[0].squeeze(0).numpy()
    fig, ax = plt.subplots(1, 2, figsize=(6, 3.4), dpi=80)
    for a, Q, ti in [(ax[0], g, "GT (Kinect)"), (ax[1], pred, "Predicho (CSI->IA)")]:
        h, v = frontal(Q); a.scatter(h, v, s=2, c=np.linalg.norm(Q, axis=1), cmap="viridis")
        a.set_title(ti, fontsize=8); a.set_aspect("equal"); a.set_xticks([]); a.set_yticks([])
        for s in a.spines.values(): s.set_visible(False)
    fig.suptitle("Sentadilla - frame %d" % (i + 1), fontsize=8); fig.tight_layout()
    buf = io.BytesIO(); fig.savefig(buf, format="png"); plt.close(fig)
    buf.seek(0); frames_gif.append(Image.open(buf).convert("P", palette=Image.ADAPTIVE))

dst = os.path.join(OUT, "sentadilla_gt_vs_pred.gif")
frames_gif[0].save(dst, save_all=True, append_images=frames_gif[1:], duration=120, loop=0, optimize=True)
print("GIF ->", dst, "| %d frames | Chamfer val %.4f m" % (len(frames_gif), np.mean(chamfs)))
