# -*- coding: utf-8 -*-
"""
entrenar_v2.py  -  Entrena el modelo CSI2PointCloud (arquitectura de Maata et al.)
con el dataset propio (ESP32 + Kinect) en formato MM-Fi.

Split 70/15/15 CRONOLOGICO POR ACCION:
  Dentro de cada accion A##, los frames se ordenan por tiempo y se parten:
    primer 70%  -> train
    siguiente 15% -> val
    ultimo 15%  -> test   (reservado; las metricas finales las saca test.py)
  Asi todas las acciones estan en los tres conjuntos y NO hay fuga temporal
  (frames vecinos casi identicos nunca se reparten entre train y test).

Uso:  python entrenar_v2.py [epocas]      (por defecto 60)
Salidas en resultados/:  modelo/csi2pc_v2.pth, curva_perdida.png, pred_vs_gt.png, split.json
"""
import os, sys, glob, time, json
import numpy as np, scipy.io as scio, torch
from torch.utils.data import Dataset, DataLoader, Subset
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---- rutas: por defecto usan el modelo y el dataset INCLUIDOS en este repo ----
_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("CSI2PC_REPO", os.path.join(_HERE, "..", "csi2pointcloud"))
ROOT = os.environ.get("CSI2PC_DATA", os.path.join(_HERE, "..", "mmfi_dataset"))
OUT  = os.environ.get("CSI2PC_OUT",  os.path.join(_HERE, "resultados"))
os.makedirs(OUT, exist_ok=True)
sys.path.append(REPO)
from src.csi2pointcloud.csi2pointcloud_arch01 import CSI2PointCloudModel
from src.loss.mmslab_loss import CSI2PointCloudLoss

EPOCHS = int(sys.argv[1]) if len(sys.argv) > 1 else 40   # alineado a Maata (checkpoint_epoch_41)
BATCH  = 8
SPLIT  = (0.70, 0.15, 0.15)   # train / val / test
torch.manual_seed(0); np.random.seed(0)


class CSIDataset(Dataset):
    """Carga pares (CSI, nube). Guarda la accion de cada item para el split por-accion."""
    def __init__(self, root):
        self.items, self.actions = [], []
        for mat in sorted(glob.glob(os.path.join(root, "**", "wifi-csi", "*.mat"), recursive=True)):
            b = mat.replace("wifi-csi", "lidar").replace(".mat", ".bin")
            if os.path.exists(b):
                # .../E01/S01/A0X/wifi-csi/frameNNN.mat  -> accion = A0X
                action = os.path.basename(os.path.dirname(os.path.dirname(mat)))
                self.items.append((mat, b)); self.actions.append(action)

    def __len__(self): return len(self.items)

    def __getitem__(self, i):
        mat, binf = self.items[i]
        m = scio.loadmat(mat)
        # Normalizacion IGUAL que Maata (mmfi.py): inf/NaN -> media, amplitud min-max [0,1], fase cruda
        amp = m["CSIamp"].astype(np.float64); pha = m["CSIphase"].astype(np.float64)
        amp[np.isinf(amp)] = np.nan; pha[np.isinf(pha)] = np.nan
        if np.any(np.isnan(amp)): amp[np.isnan(amp)] = np.nanmean(amp)
        if np.any(np.isnan(pha)): pha[np.isnan(pha)] = np.nanmean(pha)
        amp = (amp - np.nanmin(amp)) / (np.nanmax(amp) - np.nanmin(amp) + 1e-9)
        csi = np.stack([amp, pha], axis=2).astype(np.float32)   # [3,114,2,10]
        x = torch.from_numpy(csi); x = (x - x.mean()) / (x.std() + 1e-9)
        gt = np.frombuffer(open(binf, "rb").read(), dtype=np.float64).reshape(-1, 3).astype(np.float32)
        g = torch.from_numpy(gt.copy()); g = (g - g.mean()) / (g.std() + 1e-9)
        return x, g


def split_por_accion(ds, ratios):
    """Indices train/val/test, CRONOLOGICOS dentro de cada accion."""
    tr, va, te = [], [], []
    acts = np.array(ds.actions)
    for a in sorted(set(ds.actions)):
        idx = np.where(acts == a)[0]           # ya vienen ordenados por frame (tiempo)
        n = len(idx); n_tr = int(ratios[0] * n); n_va = int(ratios[1] * n)
        tr += idx[:n_tr].tolist()
        va += idx[n_tr:n_tr + n_va].tolist()
        te += idx[n_tr + n_va:].tolist()
    return tr, va, te


def plot_nube(ax, P, titulo):
    """Colores de Maata: viridis segun distancia al sensor. Orientacion de pie (X, Z, -Y)."""
    h, prof, alt = P[:, 0], P[:, 2], -P[:, 1]
    dist = np.linalg.norm(P, axis=1)
    ax.scatter(h, prof, alt, c=dist, cmap="viridis", s=7, alpha=0.9)
    ax.set_title(titulo, fontsize=13)
    ax.set_xlabel("X"); ax.set_ylabel("Z"); ax.set_zlabel("altura (-Y)")
    ax.view_init(elev=12, azim=-75)


if __name__ == "__main__":
    ds = CSIDataset(ROOT)
    tr, va, te = split_por_accion(ds, SPLIT)
    train_dl = DataLoader(Subset(ds, tr), batch_size=BATCH, shuffle=True)
    val_dl   = DataLoader(Subset(ds, va), batch_size=BATCH)

    # guardar el split para que test.py use EXACTAMENTE el mismo test
    json.dump({"ratios": SPLIT, "train": tr, "val": va, "test": te,
               "acciones": sorted(set(ds.actions))},
              open(os.path.join(OUT, "split.json"), "w"))
    print("Frames: %d | train %d | val %d | test %d | acciones %s | EPOCHS %d"
          % (len(ds), len(tr), len(va), len(te), sorted(set(ds.actions)), EPOCHS), flush=True)

    model = CSI2PointCloudModel(256, 4, 3, 3, 1200, 3, 114, 10)
    loss_fn = CSI2PointCloudLoss()
    opt = torch.optim.NAdam(model.parameters(), lr=1e-4)

    hist_tr, hist_val, best = [], [], None
    for ep in range(EPOCHS):
        t0 = time.time(); model.train(); tl = []
        for x, g in train_dl:
            opt.zero_grad(); pred, tf = model(x); loss = loss_fn(pred, g, tf)
            loss.backward(); opt.step(); tl.append(loss.item())
        model.eval(); vl = []
        with torch.no_grad():
            for x, g in val_dl:
                pred, tf = model(x); vl.append(loss_fn(pred, g, tf).item())
        hist_tr.append(float(np.mean(tl))); hist_val.append(float(np.mean(vl)) if vl else float("nan"))
        print("Epoca %3d/%d | train %.1f | val %.1f | %.1fs"
              % (ep + 1, EPOCHS, hist_tr[-1], hist_val[-1], time.time() - t0), flush=True)
        # guardar el mejor por val
        if best is None or hist_val[-1] < best:
            best = hist_val[-1]
            os.makedirs(os.path.join(OUT, "modelo"), exist_ok=True)
            torch.save({"model_state_dict": model.state_dict(), "epochs": ep + 1},
                       os.path.join(OUT, "modelo", "csi2pc_v2.pth"))

    # curva de perdida
    plt.figure(figsize=(8, 4)); plt.plot(hist_tr, label="train"); plt.plot(hist_val, label="val")
    plt.xlabel("epoca"); plt.ylabel("perdida (Chamfer + reg)"); plt.legend(); plt.grid(True)
    plt.title("Entrenamiento CSI2PointCloud (6 clases)")
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "curva_perdida.png"), dpi=120); plt.close()

    # prediccion vs ground-truth (colores de Maata)
    model.eval()
    sub_val = Subset(ds, va)
    x, g = sub_val[0] if len(sub_val) else ds[0]
    with torch.no_grad(): pred, _ = model(x.unsqueeze(0))
    pred = pred.squeeze(0).numpy(); gt = g.numpy()
    fig = plt.figure(figsize=(13, 6))
    plot_nube(fig.add_subplot(1, 2, 1, projection="3d"), gt,   "Ground-truth (Kinect)")
    plot_nube(fig.add_subplot(1, 2, 2, projection="3d"), pred, "Predicho (CSI -> IA)")
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "pred_vs_gt.png"), dpi=120); plt.close()

    print("LISTO. Mejor modelo (val=%.1f) y graficas en: %s" % (best, OUT), flush=True)
    print("  modelo/csi2pc_v2.pth | curva_perdida.png | pred_vs_gt.png | split.json", flush=True)
    print("  Ahora corre:  python test.py   (metricas ICP sobre el TEST reservado)", flush=True)
