# -*- coding: utf-8 -*-
"""Visor EN VIVO de la persona aislada (matplotlib). Cierra la ventana para salir.
Uso:  python visor_persona_vivo.py [min_range] [max_range]"""
import sys, numpy as np
import matplotlib
matplotlib.use("TkAgg")               # backend con ventana (Open3D GL no corre aqui)
import matplotlib.pyplot as plt
import kinect_capture_pointcloud as K

MINR = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
MAXR = float(sys.argv[2]) if len(sys.argv) > 2 else 2.2

k = K.open_sensor()
plt.ion()
fig, (axc, axp) = plt.subplots(1, 2, figsize=(11, 6))
fig.suptitle("Kinect en vivo  -  izq: CRUDO   der: PERSONA AISLADA   (cierra para salir)")
print(">> Visor en vivo abierto. Ponte frente a la camara. Cierra la ventana para terminar.")

try:
    while plt.fignum_exists(fig.number):
        P, C = K.capture_one_raw_frame(k, MINR, MAXR)
        if P is None or len(P) == 0:
            plt.pause(0.05); continue
        persona = K.isolate_person(P, C)

        axc.clear(); axp.clear()
        axc.scatter(P[:, 0], -P[:, 1], s=2, c=np.linalg.norm(P, axis=1), cmap="viridis")
        axc.set_title("CRUDO (%d pts)" % len(P)); axc.set_aspect("equal")
        axc.set_xticks([]); axc.set_yticks([])
        if len(persona):
            axp.scatter(persona[:, 0], -persona[:, 1], s=3,
                        c=np.linalg.norm(persona, axis=1), cmap="viridis")
            alto = persona[:, 1].max() - persona[:, 1].min()
            axp.set_title("PERSONA (%d pts, %.2fm)" % (len(persona), alto))
        else:
            axp.set_title("PERSONA: (vacio - no detectada)")
        axp.set_aspect("equal"); axp.set_xticks([]); axp.set_yticks([])
        plt.pause(0.03)
except KeyboardInterrupt:
    pass
finally:
    k.stop()
    print(">> Visor cerrado.")
