# -*- coding: utf-8 -*-
"""
kinect_capture_pointcloud.py  (v2 - captura del ENTORNO COMPLETO, en secuencia)

Graba una SECUENCIA de frames de nube de puntos desde un Azure Kinect DK,
capturando la escena completa (persona + muebles + paredes visibles), SIN
recortar solo a la persona (no se usa el Body Tracking SDK aqui a proposito).

Por cada frame genera:
  - frame{idx:03d}.bin  -> nube de puntos de N puntos fijos (float64, forma
                            (N,3) guardada como bytes crudos con .tofile()),
                            EXACTAMENTE el mismo formato binario que usa
                            mmfi.py para leer el LiDAR de MM-Fi
                            (np.frombuffer(raw, dtype=np.float64).reshape(-1,3)),
                            para que puedas conectarlo casi directo al
                            dataloader existente de csi2pointcloud.
  - timestamps.csv      -> timestamp del RELOJ DE TU PC por cada frame, para
                            poder alinear despues estos frames con los logs
                            CSI de tus ESP32 (que tambien deberias timestampear
                            frames, solo para poder inspeccionar visualmente
                            que se este capturando el entorno completo.

Requisitos (instalar en la maquina donde este conectado el Kinect):

    1) Azure Kinect Sensor SDK (K4A) instalado a nivel de sistema operativo:
       - Ubuntu: seguir la guia oficial de Microsoft para el repo de paquetes
         (libk4a1.4, libk4a1.4-dev, k4a-tools).
       - Windows: instalador oficial "Azure Kinect SDK".

    2) Paquetes de Python:
       pip install pyk4a open3d numpy opencv-python-headless

Uso tipico (graba 30 segundos a 10Hz, igual que la tasa del paper):

    python kinect_capture_pointcloud.py --out-dir sesion01 --duration 30 --fps-target 10 --num-points 1200 --save-ply-every 10

    Vista en tiempo real (sin guardar archivos):
    python kinect_capture_pointcloud.py --live

Notas:
    - Coloca el sensor fijo, mirando hacia el area donde se movera el sujeto,
      dentro del rango util 0.5m - 5.46m (modo NFOV_2X2BINNED: mismo campo de
      vision angosto que NFOV_UNBINNED, pero con mayor alcance a cambio de
      menor resolucion de profundidad, 320x288 en vez de 640x576).
    - Este script NO segmenta a la persona: guarda TODO lo que el sensor ve
      (entorno completo), tal como el LiDAR del paper original.
"""

import argparse
import os
import sys
import time

import numpy as np


def open_sensor():
    try:
        from pyk4a import PyK4A, Config, ColorResolution, DepthMode, FPS
    except ImportError:
        print("ERROR: falta el paquete 'pyk4a'. Instala con: pip install pyk4a", file=sys.stderr)
        raise

    k4a = PyK4A(
        Config(
            color_resolution=ColorResolution.RES_720P,
            depth_mode=DepthMode.NFOV_2X2BINNED,
            camera_fps=FPS.FPS_30,
            synchronized_images_only=True,
        )
    )
    k4a.start()
    return k4a


def _fill_small_depth_holes(depth, max_hole_area=400, inpaint_radius=3):
    """
    Rellena por inpainting SOLO los huecos chicos (<= max_hole_area pixeles,
    conectados por 8-vecindad) de una imagen de profundidad (uint16, mm).

    Deliberadamente NO toca huecos grandes: en una escena real, un hueco
    grande suele ser espacio vacio de verdad entre objetos separados (p.ej.
    el aire entre dos caños de un rack), y rellenarlo inventaria una
    superficie falsa uniendo cosas que en la realidad no estan conectadas.
    Los huecos chicos, en cambio, casi siempre son ruido puntual del sensor
    (flying pixels, reflejos) dentro de una misma superficie continua.
    """
    import cv2

    hole_mask = (depth == 0).astype(np.uint8)
    if not hole_mask.any():
        return depth

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(hole_mask, connectivity=8)
    small_hole_mask = np.zeros_like(hole_mask)
    for label in range(1, num_labels):
        if stats[label, cv2.CC_STAT_AREA] <= max_hole_area:
            small_hole_mask[labels == label] = 255

    if not small_hole_mask.any():
        return depth

    inpainted = cv2.inpaint(depth, small_hole_mask, inpaint_radius, cv2.INPAINT_NS)
    filled = depth.copy()
    filled[small_hole_mask > 0] = inpainted[small_hole_mask > 0]
    return filled


def capture_one_raw_frame(k4a, min_range_m=0.0, max_range_m=None):
    """
    Devuelve (points, colors) de UN frame, ya en metros y con solo los
    puntos con profundidad valida (Z > 0). No filtra por persona: es el
    entorno completo visible desde el sensor.

    min_range_m/max_range_m: banda de distancia util al sensor (metros).
    Por defecto no filtra nada (0.0 a infinito) - ajustalo segun donde este
    parado el sujeto respecto al sensor (parametros --min-range/--max-range
    en main()).
    """
    from pyk4a.transformation import depth_image_to_point_cloud

    capture = k4a.get_capture()
    if capture.depth is None or capture.color is None:
        return None, None

    # transformed_depth esta alineado a la resolucion de la camara de color,
    # asi que el color debe salir de capture.color (nativo), no de
    # transformed_color (que esta alineado a la resolucion de profundidad y
    # tiene una forma distinta -> mezclarlos revienta el filtrado por mascara).
    filled_depth = _fill_small_depth_holes(capture.transformed_depth)
    points_mm = depth_image_to_point_cloud(filled_depth, k4a.calibration, True, calibration_type_depth=False)
    points = points_mm.reshape(-1, 3).astype(np.float64) / 1000.0  # mm -> metros

    # Azure Kinect entrega el color en formato BGRA; se invierte a RGB.
    colors = capture.color[..., :3][..., ::-1].reshape(-1, 3).astype(np.float64) / 255.0

    valid_mask = points[:, 2] > min_range_m
    if max_range_m is not None:
        valid_mask &= points[:, 2] <= max_range_m
    points, colors = points[valid_mask], colors[valid_mask]

    if points.shape[0] == 0:
        return points, colors

    return _remove_statistical_outliers(points, colors)


def _remove_statistical_outliers(points, colors, voxel_size=0.02, nb_neighbors=20, std_ratio=3.0):
    """
    Limpia ruido de profundidad (p.ej. "flying pixels" en superficies vistas
    en angulo rasante o cerca del limite de rango del sensor): para cada
    punto compara su distancia promedio a sus 'nb_neighbors' vecinos mas
    cercanos contra la del resto de la nube, y descarta los que se alejan
    mas de 'std_ratio' desviaciones estandar (outliers aislados/ruidosos).

    Antes de filtrar se hace un voxel_down_sample (voxel_size en metros):
    reduce la nube de ~370k a unos pocos miles/decenas de miles de puntos,
    lo que evita que la busqueda de vecinos mas cercanos (KDTree) sea el
    cuello de botella (bajaba a ~5 FPS en vivo sin este paso).
    """
    import open3d as o3d

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd.colors = o3d.utility.Vector3dVector(colors)

    # voxel_size fijo (2cm) asume una escena a escala de cuarto (metros). Si
    # todo lo valido del frame cae muy cerca del sensor, la nube real ocupa
    # solo unos pocos cm de lado a lado, y ese mismo voxel de 2cm la reduce
    # a casi nada (una escena de 5x1x6cm entra en un puñado de celdas). Se
    # achica el voxel proporcionalmente al tamano real de la nube de este
    # frame para no perder densidad quede cual sea la escala de la escena.
    bbox_diag = np.linalg.norm(points.max(axis=0) - points.min(axis=0))
    effective_voxel_size = min(voxel_size, max(bbox_diag / 200.0, 0.001))

    if effective_voxel_size > 0:
        pcd = pcd.voxel_down_sample(effective_voxel_size)

    pcd_clean, _ = pcd.remove_statistical_outlier(nb_neighbors=nb_neighbors, std_ratio=std_ratio)
    return np.asarray(pcd_clean.points), np.asarray(pcd_clean.colors)


def isolate_person(points, colors=None, voxel=0.03):
    """
    Deja SOLO los puntos de la persona: quita piso y paredes (planos grandes)
    y se queda con el cluster compacto y vertical (la persona). Si no hay una
    persona clara (p.ej. 'habitacion sola'), devuelve un arreglo vacio (0,3)
    -> el llamador lo trata como nube minima/vacia (baseline sin persona).

    Pensado para el caso en que el target es la persona aislada (como el LiDAR
    de MM-Fi), no la escena completa.
    """
    import open3d as o3d

    if points is None or len(points) < 60:
        return np.zeros((0, 3))

    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd = pcd.voxel_down_sample(voxel)

    # Quitar SOLO las PAREDES: planos con normal HORIZONTAL (|n_y|<0.35), es decir
    # superficies verticales. Se CONSERVAN la persona y el PISO (plano horizontal,
    # normal vertical). Hasta 3 paredes.
    for _ in range(3):
        if len(pcd.points) < 300:
            break
        try:
            modelo, inl = pcd.segment_plane(0.03, 3, 80)
        except Exception:
            break
        n = np.array(modelo[:3]); n = n / (np.linalg.norm(n) + 1e-9)
        if abs(n[1]) < 0.35 and len(inl) > 0.15 * len(pcd.points):   # pared (vertical)
            pcd = pcd.select_by_index(inl, invert=True)
        else:
            break

    if len(pcd.points) < 40:
        return np.zeros((0, 3))

    # Quitar clusters chicos sueltos (muebles), mantener los grandes = persona + piso.
    lab = np.array(pcd.cluster_dbscan(0.15, 10))
    pts = np.asarray(pcd.points)
    if lab.max() < 0:
        return pts if len(pts) >= 50 else np.zeros((0, 3))

    counts = np.bincount(lab[lab >= 0])
    grandes = [i for i, c in enumerate(counts) if c >= 0.15 * counts.max()]
    keep = np.where(np.isin(lab, grandes))[0]
    q = pts[keep]
    return q if len(q) >= 50 else np.zeros((0, 3))


def point_stats(points):
    """
    Estadisticas basicas de distancia/posicion de un frame ya generado, para
    poder medir e inspeccionar lo que efectivamente esta capturando el
    sensor (rango de X/Y/Z en metros, distancia minima/maxima/promedio).
    """
    return {
        "n": int(points.shape[0]),
        "x_min": float(points[:, 0].min()), "x_max": float(points[:, 0].max()),
        "y_min": float(points[:, 1].min()), "y_max": float(points[:, 1].max()),
        "z_min": float(points[:, 2].min()), "z_max": float(points[:, 2].max()),
        "z_mean": float(points[:, 2].mean()),
    }


def run_live_view(min_range_m=0.0, max_range_m=None):
    """
    Abre una ventana de Open3D y actualiza la nube de puntos en tiempo real
    mientras el Kinect sigue capturando (entorno completo, sin guardar nada).
    Cierra la ventana o presiona Ctrl+C en la consola para salir.
    """
    import open3d as o3d

    k4a = open_sensor()

    vis = o3d.visualization.VisualizerWithKeyCallback()
    vis.create_window("Kinect - nube de puntos en vivo (cierra la ventana o Ctrl+C para salir)")
    # Con el tamano de punto por defecto de Open3D (5px) los puntos se
    # solapan entre si a la densidad tipica de esta nube, dando la
    # impresion visual de una superficie solida en vez de una nube de
    # puntos dispersos. Se achica para que cada punto se distinga.
    vis.get_render_option().point_size = 2.0
    pcd = o3d.geometry.PointCloud()
    geometry_added = False
    frame_count = 0
    skipped_count = 0

    print(">> Vista en vivo iniciada. Cierra la ventana o presiona Ctrl+C para salir.")
    try:
        while True:
            points, colors = capture_one_raw_frame(k4a, min_range_m, max_range_m)

            if points is not None and points.shape[0] > 0:
                pcd.points = o3d.utility.Vector3dVector(points)
                pcd.colors = o3d.utility.Vector3dVector(colors)

                if not geometry_added:
                    vis.add_geometry(pcd)
                    geometry_added = True

                    # Open3D por defecto mira de canto contra la escena (a lo
                    # largo del eje Z de profundidad), lo que hace que
                    # cualquier objeto angosto en esa direccion (una persona,
                    # muebles) colapse visualmente en una linea delgada o un
                    # "hueco", aunque los puntos esten bien calculados. Se
                    # fuerza un angulo 3/4 desde arriba para que la escena se
                    # perciba en 3D desde el primer frame (podes seguir
                    # rotando con el mouse despues).
                    ctr = vis.get_view_control()
                    ctr.set_lookat(pcd.get_center())
                    ctr.set_front([0.3, -0.6, -0.75])
                    ctr.set_up([0.0, -1.0, 0.0])
                    ctr.set_zoom(0.7)
                else:
                    vis.update_geometry(pcd)

                frame_count += 1
                if frame_count % 30 == 0:
                    s = point_stats(points)
                    print(f">> Frames renderizados: {frame_count} ({s['n']} puntos, "
                          f"Z=[{s['z_min']:.2f},{s['z_max']:.2f}]m, distancia promedio={s['z_mean']:.2f}m)")
            else:
                skipped_count += 1
                if skipped_count % 30 == 0:
                    print(f">> Aviso: {skipped_count} capturas seguidas sin depth/color validos.")

            # Siempre hay que procesar eventos de la ventana, aunque el frame
            # actual no tenga datos validos; si no, la ventana se congela.
            if not vis.poll_events():
                break
            vis.update_renderer()
    except KeyboardInterrupt:
        print(">> Vista en vivo interrumpida por el usuario.")
    finally:
        vis.destroy_window()
        k4a.stop()


def fix_point_count(points, num_points):
    """
    Misma logica que usa mmfi.py (src/mmfi/mmfi_lib/mmfi.py) para el LiDAR
    de MM-Fi: submuestreo aleatorio si sobran puntos, padding estadistico
    por eje si faltan.
    """
    n = points.shape[0]
    if n == 0:
        raise ValueError("Frame sin puntos validos (0 puntos con profundidad).")

    if n >= num_points:
        indices = np.random.choice(n, num_points, replace=False)
        return points[indices, :]

    num_pad = num_points - n
    mean_x, mean_y, mean_z = points[:, 0].mean(), points[:, 1].mean(), points[:, 2].mean()
    std_z = points[:, 2].std()
    min_x, max_x = points[:, 0].min(), points[:, 0].max()
    min_y, max_y = points[:, 1].min(), points[:, 1].max()

    new_points = np.zeros((num_pad, 3))

    x_values = np.random.normal(loc=mean_x, scale=(max_x - min_x) / 4 + 1e-9, size=num_pad)
    new_points[:, 0] = np.clip(x_values, min_x, max_x)

    y_values = np.random.normal(loc=mean_y, scale=(max_y - min_y) / 4 + 1e-9, size=num_pad)
    new_points[:, 1] = np.clip(y_values, min_y, max_y)

    std_z_half = std_z / 2
    z_mask = (points[:, 2] >= mean_z - std_z_half) & (points[:, 2] <= mean_z + std_z_half)
    z_avg = points[z_mask, 2].mean() if np.any(z_mask) else mean_z
    new_points[:, 2] = z_avg

    return np.vstack((points, new_points))


def save_preview_ply(points, colors, path):
    import open3d as o3d
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    pcd.colors = o3d.utility.Vector3dVector(colors)
    o3d.io.write_point_cloud(path, pcd)


def main():
    parser = argparse.ArgumentParser(description="Captura una secuencia de nubes de puntos del ENTORNO COMPLETO con Azure Kinect DK.")
    parser.add_argument("--out-dir", type=str, default="kinect_capture", help="Carpeta de salida para los frames y timestamps.")
    parser.add_argument("--num-points", type=int, default=1200, help="Numero fijo de puntos por frame (por defecto 1200, igual que el paper).")
    parser.add_argument("--fps-target", type=float, default=10.0, help="Tasa de guardado en Hz (por defecto 10Hz, igual que MM-Fi/el paper).")
    parser.add_argument("--duration", type=float, default=30.0, help="Duracion total de la grabacion, en segundos.")
    parser.add_argument("--save-ply-every", type=int, default=0, help="Si > 0, ademas guarda un .ply de la nube CRUDA (con color) cada N frames, para inspeccion visual. 0 = nunca.")
    parser.add_argument("--live", action="store_true", help="Abre una ventana con la nube de puntos en tiempo real (no guarda archivos, ignora el resto de las opciones).")
    parser.add_argument("--min-range", type=float, default=1.5, help="Distancia minima al sensor a conservar, en metros (descarta mas cerca). Por defecto 1.5m (banda alrededor de 2m).")
    parser.add_argument("--max-range", type=float, default=2.5, help="Distancia maxima al sensor a conservar, en metros (descarta mas lejos). Por defecto 2.5m (banda alrededor de 2m).")
    parser.add_argument("--solo-persona", action="store_true", help="Aisla SOLO la persona (quita piso/paredes). Si no hay persona (habitacion sola) guarda una nube minima/vacia.")
    parser.add_argument("--warmup", type=float, default=0.0, help="Segundos iniciales a DESCARTAR (no guarda nada) para que se estabilicen WiFi/Kinect/pose.")
    args = parser.parse_args()

    if args.live:
        run_live_view(args.min_range, args.max_range)
        return

    os.makedirs(args.out_dir, exist_ok=True)
    timestamps_path = os.path.join(args.out_dir, "timestamps.csv")

    print(f">> Abriendo Azure Kinect DK (modo NFOV_2X2BINNED, 30 FPS de sensor, guardando a {args.fps_target} Hz)...")
    k4a = open_sensor()

    frame_interval = 1.0 / args.fps_target
    t_start = time.time()
    idx = 0

    try:
        with open(timestamps_path, "w") as f_ts:
            f_ts.write("frame_idx,host_timestamp,n_puntos_crudos,x_min,x_max,y_min,y_max,z_min,z_max,z_promedio\n")

            while (time.time() - t_start) < args.duration:
                t_frame_start = time.time()

                points, colors = capture_one_raw_frame(k4a, args.min_range, args.max_range)
                if points is None or points.shape[0] == 0:
                    print("  [!] Frame invalido (sin datos de profundidad/color sincronizados), se salta.")
                    continue

                # descarte de calentamiento: no guardar los primeros --warmup segundos
                if (time.time() - t_start) < args.warmup:
                    continue

                if args.solo_persona:
                    persona = isolate_person(points, colors)
                    if persona.shape[0] >= 50:
                        points = persona
                        points_fixed = fix_point_count(points, args.num_points)
                    else:
                        # sin persona (p.ej. habitacion sola) -> nube minima en el origen
                        points = np.zeros((1, 3))
                        points_fixed = np.zeros((args.num_points, 3))
                    s = point_stats(points)
                else:
                    s = point_stats(points)
                    points_fixed = fix_point_count(points, args.num_points)

                idx += 1
                bin_path = os.path.join(args.out_dir, f"frame{idx:03d}.bin")
                points_fixed.astype(np.float64).tofile(bin_path)

                host_ts = time.time()
                f_ts.write(
                    f"{idx},{host_ts:.6f},{s['n']},{s['x_min']:.4f},{s['x_max']:.4f},"
                    f"{s['y_min']:.4f},{s['y_max']:.4f},{s['z_min']:.4f},{s['z_max']:.4f},{s['z_mean']:.4f}\n"
                )
                f_ts.flush()

                stats_txt = f"Z=[{s['z_min']:.2f},{s['z_max']:.2f}]m dist.prom={s['z_mean']:.2f}m"
                if args.save_ply_every > 0 and idx % args.save_ply_every == 0:
                    preview_path = os.path.join(args.out_dir, f"frame{idx:03d}_preview.ply")
                    save_preview_ply(points, colors, preview_path)
                    print(f"  >> Frame {idx:03d}: {points.shape[0]} puntos crudos -> {args.num_points} fijos | {stats_txt} | preview: {preview_path}")
                else:
                    print(f"  >> Frame {idx:03d}: {points.shape[0]} puntos crudos -> {args.num_points} fijos | {stats_txt}")

                elapsed = time.time() - t_frame_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
    finally:
        k4a.stop()

    print(f"\n>> Listo. {idx} frames guardados en '{args.out_dir}/' (formato .bin compatible con mmfi.py).")
    print(f">> Timestamps del host en '{timestamps_path}' — usalos para alinear estos frames con el CSI de tus ESP32.")


if __name__ == "__main__":
    main()
