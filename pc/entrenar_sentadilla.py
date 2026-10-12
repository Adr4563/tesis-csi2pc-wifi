# -*- coding: utf-8 -*-
"""
Entrena SOLO con la actividad de sentadillas (A03), dataset completo.
- Split de Maata: random_split con ratio 0.8 (semilla 0) -> 80% train / 20% val.
- 30 epocas, arquitectura 256 (CSI2PointCloudModel 256, 4, 3, 3), NAdam lr 1e-4.
- Guarda checkpoint cada epoca (best por val + last), log y curva de perdida.
Objetivo: ver cuanto baja el Chamfer y como se mueven los puntos en la sentadilla.
"""
import os, sys, glob, time, json
import numpy as np, scipy.io as scio, torch
from torch.utils.data import Dataset, DataLoader, Subset

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..", "tesis", "modelo")
DATA = os.environ.get("CSI2PC_DATA", r"C:\Users\user\Desktop\Carpeta_Trabajo\capturas_sync\mmfi_dataset")
OUT  = os.path.join(HERE, "resultados_sentadilla")
os.makedirs(os.path.join(OUT, "modelo"), exist_ok=True)
sys.path.insert(0, REPO)
from csi2pointcloud.csi2pointcloud_arch01 import CSI2PointCloudModel
from loss.mmslab_loss import CSI2PointCloudLoss

EPOCHS = 30
BATCH  = 8
RATIO  = 0.8          # split de Maata (random_split ratio)
SEED   = 0            # random_seed de Maata
torch.manual_seed(SEED); np.random.seed(SEED)


class CSIDataset(Dataset):
    def __init__(self, root, accion="A03"):
        self.items = []
        for mat in sorted(glob.glob(os.path.join(root, "**", accion, "wifi-csi", "*.mat"), recursive=True)):
            b = mat.replace("wifi-csi", "lidar").replace(".mat", ".bin")
            if os.path.exists(b): self.items.append((mat, b))
    def __len__(self): return len(self.items)
    def __getitem__(self, i):
        mat, binf = self.items[i]
        m = scio.loadmat(mat)
        amp = m["CSIamp"].astype(np.float64); pha = m["CSIphase"].astype(np.float64)
        amp[np.isinf(amp)] = np.nan; pha[np.isinf(pha)] = np.nan
        if np.any(np.isnan(amp)): amp[np.isnan(amp)] = np.nanmean(amp)
        if np.any(np.isnan(pha)): pha[np.isnan(pha)] = np.nanmean(pha)
        amp = (amp - np.nanmin(amp)) / (np.nanmax(amp) - np.nanmin(amp) + 1e-9)
        csi = np.stack([amp, pha], axis=2).astype(np.float32)
        x = torch.from_numpy(csi); x = (x - x.mean()) / (x.std() + 1e-9)
        gt = np.frombuffer(open(binf, "rb").read(), dtype=np.float64).reshape(-1, 3).astype(np.float32)
        g = torch.from_numpy(gt.copy()); g = (g - g.mean()) / (g.std() + 1e-9)
        return x, g


if __name__ == "__main__":
    ds = CSIDataset(DATA, "A03")
    n = len(ds)
    # split de Maata: random_split ratio 0.8
    idx = np.random.permutation(n)
    n_tr = int(np.floor(RATIO * n))
    tr, va = idx[:n_tr].tolist(), idx[n_tr:].tolist()
    json.dump({"train": tr, "val": va, "ratio": RATIO, "seed": SEED, "accion": "A03"},
              open(os.path.join(OUT, "split.json"), "w"))
    print("SOLO SENTADILLAS (A03) | pares %d | train %d | val %d | EPOCHS %d (arch 256, split Maata 0.8)"
          % (n, len(tr), len(va), EPOCHS), flush=True)

    train_dl = DataLoader(Subset(ds, tr), batch_size=BATCH, shuffle=True)
    val_dl   = DataLoader(Subset(ds, va), batch_size=BATCH)

    model = CSI2PointCloudModel(256, 4, 3, 3, 1200, 3, 114, 10)
    loss_fn = CSI2PointCloudLoss()
    opt = torch.optim.NAdam(model.parameters(), lr=1e-4)

    hist = {"train": [], "val": []}
    best = None
    for ep in range(EPOCHS):
        t0 = time.time(); model.train(); tl = []
        for x, g in train_dl:
            opt.zero_grad(); pred, tf = model(x); loss = loss_fn(pred, g, tf)
            loss.backward(); opt.step(); tl.append(loss.item())
        model.eval(); vl = []
        with torch.no_grad():
            for x, g in val_dl:
                pred, tf = model(x); vl.append(loss_fn(pred, g, tf).item())
        hist["train"].append(float(np.mean(tl))); hist["val"].append(float(np.mean(vl)) if vl else float("nan"))
        print("Epoca %2d/%d | train %.1f | val %.1f | %.1f min" %
              (ep + 1, EPOCHS, hist["train"][-1], hist["val"][-1], (time.time() - t0) / 60), flush=True)
        json.dump(hist, open(os.path.join(OUT, "historia.json"), "w"))
        torch.save({"model_state_dict": model.state_dict(), "epoch": ep + 1},
                   os.path.join(OUT, "modelo", "csi2pc_sentadilla_last.pth"))
        if best is None or hist["val"][-1] < best:
            best = hist["val"][-1]
            torch.save({"model_state_dict": model.state_dict(), "epoch": ep + 1},
                       os.path.join(OUT, "modelo", "csi2pc_sentadilla_best.pth"))

    # curva de perdida
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    plt.figure(figsize=(8, 4)); plt.plot(hist["train"], label="train"); plt.plot(hist["val"], label="val")
    plt.xlabel("epoca"); plt.ylabel("perdida (Chamfer + reg)"); plt.legend(); plt.grid(True)
    plt.title("Entrenamiento sentadillas (A03) - 30 epocas")
    plt.tight_layout(); plt.savefig(os.path.join(OUT, "curva_perdida.png"), dpi=120)
    print("LISTO. Mejor val = %.2f | modelo y curva en %s" % (best, OUT), flush=True)
