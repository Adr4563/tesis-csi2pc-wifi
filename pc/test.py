# -*- coding: utf-8 -*-
"""
test.py  -  Metricas del modelo entrenado sobre el conjunto de TEST reservado
(el ultimo 15% cronologico de cada accion, que el modelo nunca vio).

Metricas ICP propias (criterio del proyecto, NO el protocolo de Maata):
  - ICP fitness : fraccion de puntos con correspondencia dentro de UMBRAL (en metros)
  - ICP RMSE    : error cuadratico medio de esas correspondencias (en metros)
  - Chamfer     : distancia bidireccional media (referencia de reconstruccion)

Uso:  python test.py [umbral_m]   (umbral por defecto 0.10 m)
"""
import os, sys, glob, json
import numpy as np, scipy.io as scio, torch
import open3d as o3d

REPO = os.environ.get("CSI2PC_REPO", r"C:\Users\user\Desktop\Carpeta_Trabajo\csi2pointcloud")
ROOT = os.environ.get("CSI2PC_DATA", r"C:\Users\user\Desktop\Carpeta_Trabajo\capturas_sync\mmfi_dataset")
OUT  = os.environ.get("CSI2PC_OUT",  os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados"))
CKPT = os.path.join(OUT, "modelo", "csi2pc_v2.pth")
sys.path.append(REPO)
from src.csi2pointcloud.csi2pointcloud_arch01 import CSI2PointCloudModel

THR = float(sys.argv[1]) if len(sys.argv) > 1 else 0.10   # umbral de correspondencia (metros)

# mismo orden de items que en el entrenamiento
items, actions = [], []
for mat in sorted(glob.glob(os.path.join(ROOT, "**", "wifi-csi", "*.mat"), recursive=True)):
    b = mat.replace("wifi-csi", "lidar").replace(".mat", ".bin")
    if os.path.exists(b):
        items.append((mat, b))
        actions.append(os.path.basename(os.path.dirname(os.path.dirname(mat))))

# indices de TEST (del split.json que dejo entrenar_v2.py)
sp = json.load(open(os.path.join(OUT, "split.json")))
test_idx = sp["test"]

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


def nn_dist(A, B):
    kdt = o3d.geometry.KDTreeFlann(
        o3d.geometry.PointCloud(o3d.utility.Vector3dVector(B)))
    d = np.empty(len(A))
    for i, p in enumerate(A):
        _, _, d2 = kdt.search_knn_vector_3d(p, 1); d[i] = np.sqrt(d2[0])
    return d


por_accion = {}
fits, rmses, chamfs = [], [], []
for i in test_idx:
    gt = np.frombuffer(open(items[i][1], "rb").read(), dtype=np.float64).reshape(-1, 3).astype(np.float64)
    x = csi_tensor(items[i][0])
    with torch.no_grad():
        pred, _ = model(x.unsqueeze(0))
    pred = pred.squeeze(0).numpy().astype(np.float64)
    pred_m = pred * gt.std() + gt.mean()     # a metros, escala del GT

    # ICP point-to-point (alinea pred -> gt) para fitness/RMSE
    reg = o3d.pipelines.registration.registration_icp(
        o3d.geometry.PointCloud(o3d.utility.Vector3dVector(pred_m)),
        o3d.geometry.PointCloud(o3d.utility.Vector3dVector(gt)),
        THR, np.eye(4),
        o3d.pipelines.registration.TransformationEstimationPointToPoint())
    ch = nn_dist(pred_m, gt).mean() + nn_dist(gt, pred_m).mean()
    fits.append(reg.fitness); rmses.append(reg.inlier_rmse); chamfs.append(ch)
    por_accion.setdefault(actions[i], []).append((reg.fitness, reg.inlier_rmse, ch))

print("=" * 54)
print("METRICAS SOBRE TEST (umbral %.2f m, %d frames)" % (THR, len(fits)))
print("=" * 54)
print("  ICP fitness : %.4f" % np.mean(fits))
print("  ICP RMSE    : %.4f m" % np.mean(rmses))
print("  Chamfer     : %.4f m" % np.mean(chamfs))
print("-" * 54)
print("  Por accion:")
for a in sorted(por_accion):
    v = np.array(por_accion[a])
    print("    %s | fitness %.3f | RMSE %.4f m | Chamfer %.4f m | n=%d"
          % (a, v[:, 0].mean(), v[:, 1].mean(), v[:, 2].mean(), len(v)))

# guardar a archivo
with open(os.path.join(OUT, "metricas_test.txt"), "w") as f:
    f.write("TEST umbral %.2f m, %d frames\n" % (THR, len(fits)))
    f.write("ICP fitness %.4f | ICP RMSE %.4f m | Chamfer %.4f m\n"
            % (np.mean(fits), np.mean(rmses), np.mean(chamfs)))
    for a in sorted(por_accion):
        v = np.array(por_accion[a])
        f.write("%s fitness %.3f RMSE %.4f Chamfer %.4f n %d\n"
                % (a, v[:, 0].mean(), v[:, 1].mean(), v[:, 2].mean(), len(v)))
print("\n>> guardado: resultados/metricas_test.txt")
