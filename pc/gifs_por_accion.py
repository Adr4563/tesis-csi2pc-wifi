# -*- coding: utf-8 -*-
"""
Genera un GIF por accion (gif_A01..gif_A06) con GT vs predicho, usando el
modelo y el split que dejo entrenar_tesis.ipynb.

Replica el render de test_tesis.ipynb (misma vista, mismos ejes fijos) pero
recorre todas las acciones en una sola pasada.

Uso:
    python pc/gifs_por_accion.py                # las 6 acciones
    python pc/gifs_por_accion.py A03 A05        # solo esas
    python pc/gifs_por_accion.py --dpi 90       # mas resolucion (GIF mas pesado)

Salida: $CSI2PC_OUT/gif_<ACCION>.gif   (por defecto pc/resultados/)
"""
import argparse
import glob
import json
import os
import sys

import numpy as np
import scipy.io as scio
import torch
import matplotlib
matplotlib.use("Agg")                      # sin ventana: render a imagen
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image

AQUI  = os.path.dirname(os.path.abspath(__file__))
TESIS = os.path.abspath(os.path.join(AQUI, ".."))
MODELO = os.path.join(TESIS, "tesis")
if MODELO not in sys.path:
    sys.path.append(MODELO)
from modelo.csi2pointcloud.csi2pointcloud_arch01 import CSI2PointCloudModel  # noqa: E402

DATA = os.path.abspath(os.environ.get("CSI2PC_DATA", os.path.join(TESIS, "mmfi_dataset")))
OUT  = os.path.abspath(os.environ.get("CSI2PC_OUT", os.path.join(TESIS, "pc", "resultados")))
CKPT  = os.path.join(OUT, "modelo", "csi2pc_v2.pth")
SPLIT = os.path.join(OUT, "split.json")

NOMBRES = {"A01": "estatico", "A02": "brazos en cruz", "A03": "caminar en el sitio",
           "A04": "agacharse", "A05": "girar torso", "A06": "estirar piernas"}


def cargar_par(mat, binf):
    """Mismo preprocesamiento que el dataloader de entrenamiento/test."""
    m = scio.loadmat(mat)
    amp = m["CSIamp"].astype(np.float64)
    pha = m["CSIphase"].astype(np.float64)
    for X in (amp, pha):
        X[np.isinf(X)] = np.nan
        if np.any(np.isnan(X)):
            X[np.isnan(X)] = np.nanmean(X)
    amp = (amp - np.nanmin(amp)) / (np.nanmax(amp) - np.nanmin(amp) + 1e-9)
    csi = np.stack([amp, pha], axis=2).astype(np.float32)
    csi = (csi - csi.mean()) / (csi.std() + 1e-9)

    gt = np.frombuffer(open(binf, "rb").read(), dtype=np.float64)
    gt = gt.reshape(-1, 3).astype(np.float32).copy()
    gt = (gt - gt.mean()) / (gt.std() + 1e-9)
    return csi, gt


def limites(nubes, margen=0.05):
    P = np.vstack(nubes)
    lo, hi = P.min(axis=0), P.max(axis=0)
    d = (hi - lo) * margen
    return lo - d, hi + d


def frame_a_imagen(gt, pred, titulo, lo, hi, dpi=70):
    fig = plt.figure(figsize=(12.8, 5.4), dpi=dpi)
    fig.suptitle(titulo, fontsize=14)
    for col, (P, nombre) in enumerate([(gt, "Ground-truth (Kinect)"),
                                       (pred, "Predicho (CSI -> IA)")]):
        ax = fig.add_subplot(1, 2, col + 1, projection="3d")
        h, prof, alt = P[:, 0], P[:, 2], -P[:, 1]
        ax.scatter(h, prof, alt, c=np.linalg.norm(P, axis=1),
                   cmap="viridis", s=4, alpha=0.85)
        ax.set_xlim(lo[0], hi[0])          # ejes fijos: el GIF no "salta"
        ax.set_ylim(lo[2], hi[2])
        ax.set_zlim(-hi[1], -lo[1])
        ax.set_autoscale_on(False)
        ax.set_title(nombre, fontsize=11)
        ax.set_xlabel("X (m)"); ax.set_ylabel("Z (m)"); ax.set_zlabel("altura (m)")
        ax.view_init(elev=12, azim=-75)
    fig.tight_layout()
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    img = np.asarray(canvas.buffer_rgba())[:, :, :3].copy()
    plt.close(fig)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("acciones", nargs="*", help="A01..A06 (por defecto todas)")
    ap.add_argument("--dpi", type=int, default=70, help="resolucion (def. 70)")
    ap.add_argument("--ms", type=int, default=200, help="ms por frame (def. 200 = 5 fps)")
    args = ap.parse_args()

    for p, q in [(CKPT, "Falta el modelo. Corre entrenar_tesis.ipynb"),
                 (SPLIT, "Falta split.json. Corre entrenar_tesis.ipynb")]:
        if not os.path.exists(p):
            sys.exit("%s\n  (%s)" % (q, p))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    ck = torch.load(CKPT, map_location=device, weights_only=False)
    CFG = ck.get("config", {})
    model = CSI2PointCloudModel(
        embedding_dim=CFG.get("embedding_dim", 256),
        num_heads=CFG.get("num_heads", 4),
        num_encoder_layers=CFG.get("num_encoder_layers", 3),
        num_decoder_layers=CFG.get("num_decoder_layers", 3),
        num_points=CFG.get("num_points", 1200),
        num_antennas=CFG.get("num_antennas", 3),
        num_subcarriers=CFG.get("num_subcarriers", 114),
        num_time_slices=CFG.get("num_time_slices", 10),
    ).to(device)
    model.load_state_dict(ck["model_state_dict"])
    model.eval()
    print("Modelo: epoca %s, val loss %.4f | %s"
          % (ck.get("epochs", "?"), ck.get("val_loss", float("nan")), device))

    # Mismo orden de items que el dataloader, para que el split cuadre
    items, acts = [], []
    for mat in sorted(glob.glob(os.path.join(DATA, "**", "wifi-csi", "*.mat"),
                                recursive=True)):
        binf = mat.replace("wifi-csi", "lidar").replace(".mat", ".bin")
        if os.path.exists(binf):
            items.append((mat, binf))
            acts.append(os.path.basename(os.path.dirname(os.path.dirname(mat))))

    te = json.load(open(SPLIT))["test"]
    pedidas = [a.upper() for a in args.acciones] or sorted(set(acts[k] for k in te))

    for a in pedidas:
        idx = [k for k in te if acts[k] == a]
        if not idx:
            print("%s: sin frames en el test" % a)
            continue

        gts, preds = [], []
        with torch.no_grad():
            for k in idx:
                csi, gt = cargar_par(*items[k])
                pred, _ = model(torch.from_numpy(csi).unsqueeze(0).to(device))
                gts.append(gt)
                preds.append(pred.squeeze(0).cpu().numpy())

        lo, hi = limites(gts)
        frames = [Image.fromarray(frame_a_imagen(
            gts[j], preds[j],
            "%s %s - frame %d/%d" % (a, NOMBRES.get(a, ""), j + 1, len(idx)),
            lo, hi, dpi=args.dpi)) for j in range(len(idx))]

        ruta = os.path.join(OUT, "gif_%s.gif" % a)
        frames[0].save(ruta, save_all=True, append_images=frames[1:],
                       duration=args.ms, loop=0, optimize=True)
        print("  gif_%s.gif: %d frames, %.1f MB"
              % (a, len(frames), os.path.getsize(ruta) / 1e6))

    print("\nGIFs en %s" % OUT)


if __name__ == "__main__":
    main()
