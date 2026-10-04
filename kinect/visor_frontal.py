# -*- coding: utf-8 -*-
"""Visor en vivo con vista FRONTAL por defecto (como te ve la camara, derecho)."""
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

k = K.open_sensor()
vis = o3d.visualization.VisualizerWithKeyCallback()
vis.create_window("Kinect FRONTAL (cierra con la X)")
vis.get_render_option().point_size = 2.5
pcd = o3d.geometry.PointCloud(); added = False
try:
    while True:
        P, C = K.capture_one_raw_frame(k, MINR, MAXR)
        if P is not None and P.shape[0] > 0:
            pcd.points = o3d.utility.Vector3dVector(P)
            pcd.colors = o3d.utility.Vector3dVector(C)
            if not added:
                vis.add_geometry(pcd); added = True
                ctr = vis.get_view_control()
                ctr.set_front([0, 0, -1])   # mirar a lo largo de +Z (como la camara)
                ctr.set_up([0, -1, 0])      # arriba = -Y (Y apunta abajo)
                ctr.set_lookat(pcd.get_center())
                ctr.set_zoom(0.6)
            else:
                vis.update_geometry(pcd)
        if not vis.poll_events(): break
        vis.update_renderer()
finally:
    vis.destroy_window(); k.stop()
