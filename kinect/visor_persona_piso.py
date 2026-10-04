# -*- coding: utf-8 -*-
"""Visor en vivo: persona + piso (quita paredes/muebles). Estable, no se vacia por frame."""
import os, sys, numpy as np
for d in [r"C:\Program Files\Azure Kinect SDK v1.4.1\sdk\windows-desktop\amd64\release\bin",
          r"C:\Program Files\Azure Kinect SDK v1.4.1\tools"]:
    try: os.add_dll_directory(d)
    except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kinect_capture_pointcloud as K
import open3d as o3d

MINR = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
MAXR = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0


def persona_piso(P, C):
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(P); pcd.colors = o3d.utility.Vector3dVector(C)
    pcd = pcd.voxel_down_sample(0.04)
    # quita SOLO paredes grandes (plano con normal horizontal). Se queda persona+piso.
    for _ in range(3):
        if len(pcd.points) < 300: break
        pl, inl = pcd.segment_plane(0.03, 3, 80)
        n = np.array(pl[:3]); n = n / (np.linalg.norm(n) + 1e-9)
        if abs(n[1]) < 0.35 and len(inl) > 0.15 * len(pcd.points):
            pcd = pcd.select_by_index(inl, invert=True)   # pared -> fuera
        else:
            break
    # quita clusters chicos sueltos (muebles/pila), mantiene persona + piso (clusters grandes)
    if len(pcd.points) > 30:
        lab = np.array(pcd.cluster_dbscan(0.15, 10))
        if lab.max() >= 0:
            counts = np.bincount(lab[lab >= 0])
            grandes = [i for i, c in enumerate(counts) if c >= 0.15 * counts.max()]
            keep = np.where(np.isin(lab, grandes))[0]
            if len(keep) > 20:
                pcd = pcd.select_by_index(keep)
    return pcd


k = K.open_sensor()
vis = o3d.visualization.VisualizerWithKeyCallback()
vis.create_window("Kinect: persona + piso (cierra con la X)")
vis.get_render_option().point_size = 3.0
geo = o3d.geometry.PointCloud(); added = False
try:
    while True:
        P, C = K.capture_one_raw_frame(k, MINR, MAXR)
        if P is not None and P.shape[0] > 0:
            pcd = persona_piso(P, C)
            if len(pcd.points) >= 40:          # solo actualiza si hay suficientes puntos (NO se vacia)
                geo.points = pcd.points; geo.colors = pcd.colors
                if not added:
                    vis.add_geometry(geo); added = True
                    ctr = vis.get_view_control()
                    ctr.set_front([0, 0, -1]); ctr.set_up([0, -1, 0]); ctr.set_zoom(0.6)
                else:
                    vis.update_geometry(geo)
        if not vis.poll_events(): break
        vis.update_renderer()
finally:
    vis.destroy_window(); k.stop()
