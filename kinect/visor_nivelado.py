# -*- coding: utf-8 -*-
"""Visor en vivo AUTO-NIVELADO: detecta el piso y rota la nube para que quede derecha y de frente."""
import os, sys, numpy as np
for d in [r"C:\Program Files\Azure Kinect SDK v1.4.1\sdk\windows-desktop\amd64\release\bin",
          r"C:\Program Files\Azure Kinect SDK v1.4.1\tools"]:
    try: os.add_dll_directory(d)
    except Exception: pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kinect_capture_pointcloud as K
import open3d as o3d

MINR = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3
MAXR = float(sys.argv[2]) if len(sys.argv) > 2 else 3.5


def detectar_piso(P):
    """Plano con normal MAS vertical (piso/techo), grande -> evita paredes."""
    pcd = o3d.geometry.PointCloud(); pcd.points = o3d.utility.Vector3dVector(P)
    pcd = pcd.voxel_down_sample(0.04)
    rest = pcd; best = None
    for _ in range(4):
        if len(rest.points) < 100: break
        pl, inl = rest.segment_plane(0.03, 3, 300)
        n = np.array(pl[:3]); n = n / (np.linalg.norm(n) + 1e-9)
        score = len(inl) * abs(n[1])     # grande Y normal vertical (|n_y| alto = piso)
        if best is None or score > best[0]:
            best = (score, n)
        rest = rest.select_by_index(inl, invert=True)
    n = best[1]
    if n[1] < 0: n = -n                   # que apunte hacia ABAJO (+Y)
    return n


def rot_a(a, b):
    a = a / np.linalg.norm(a); b = b / np.linalg.norm(b)
    v = np.cross(a, b); s = np.linalg.norm(v); c = np.dot(a, b)
    if s < 1e-8: return np.eye(3)
    vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + vx + vx @ vx * ((1 - c) / (s ** 2))


k = K.open_sensor()
vis = o3d.visualization.VisualizerWithKeyCallback()
vis.create_window("Kinect NIVELADO (cierra con la X)")
vis.get_render_option().point_size = 2.0
pcd = o3d.geometry.PointCloud()
added = False; R = None; nframe = 0
print(">> Visor nivelado iniciado. Detectando piso en los primeros frames...")
try:
    while True:
        P, C = K.capture_one_raw_frame(k, MINR, MAXR)
        if P is not None and P.shape[0] > 50:
            if R is None and nframe > 5:    # tras unos frames, fija la rotacion de nivelado
                try:
                    n = detectar_piso(P)
                    R = rot_a(n, np.array([0, 1, 0]))   # piso -> horizontal
                    ang = np.degrees(np.arccos(abs(np.dot(n, [0, 1, 0]))))
                    print(">> Piso detectado. Inclinacion corregida: %.1f grados" % ang)
                except Exception as e:
                    print("   (aun buscando piso...)", e)
            Pd = (R @ P.T).T if R is not None else P
            pcd.points = o3d.utility.Vector3dVector(Pd)
            pcd.colors = o3d.utility.Vector3dVector(C)
            if not added:
                vis.add_geometry(pcd); added = True
                ctr = vis.get_view_control()
                ctr.set_front([0, 0, -1]); ctr.set_up([0, -1, 0]); ctr.set_zoom(0.7)
            else:
                vis.update_geometry(pcd)
            nframe += 1
        if not vis.poll_events(): break
        vis.update_renderer()
except KeyboardInterrupt:
    pass
finally:
    vis.destroy_window(); k.stop()
