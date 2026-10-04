# -*- coding: utf-8 -*-
"""
Captura SINCRONIZADA: Kinect (PC) + CSI de los 3 ESP32 (Pi), disparadas a la vez.
- La Kinect guarda nubes .bin + timestamps.csv con reloj PC.
- El Pi guarda CSI (rx*.csv) con reloj Pi, y se genera trafico (flood) para que
  el router transmita y los sniffers capturen mucho.
- Al final trae el CSI del Pi a la PC. El pareo (offset PC<->Pi) lo hace emparejar.py.

Uso:  python captura_sincronizada.py <duracion_seg> [nombre_sesion]
"""
import subprocess, threading, time, os, sys, datetime

DUR     = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
SESSION = sys.argv[2] if len(sys.argv) > 2 else "sesion_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

PI         = "pi@192.168.0.179"
BASE       = r"C:\Users\user\Desktop\Carpeta_Trabajo\capturas_sync"
OUT        = os.path.join(BASE, SESSION)
KINECT_DIR = r"C:\Users\user\Desktop\Carpeta_Trabajo\3d-human-pointcloud-wifi-csi\kinect"
K4A_BIN    = r"C:\Program Files\Azure Kinect SDK v1.4.1\sdk\windows-desktop\amd64\release\bin"
K4A_TOOLS  = r"C:\Program Files\Azure Kinect SDK v1.4.1\tools"
OFFSET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pc_pi_offset.txt")

os.makedirs(os.path.join(OUT, "kinect"), exist_ok=True)

# offset PC<->Pi (t_pi - t_pc)
offset = None
if os.path.exists(OFFSET_FILE):
    offset = float(open(OFFSET_FILE).read().strip())
    with open(os.path.join(OUT, "offset_pc_pi.txt"), "w") as f:
        f.write("%.6f\n" % offset)

env = os.environ.copy()
env["PATH"] = env["PATH"] + ";" + K4A_BIN + ";" + K4A_TOOLS

result = {}

def run_csi():
    # El CSI corre un poco mas largo que la Kinect (envoltura), con flood de trafico.
    dur_csi = DUR + 4
    cmd = ("python3 /home/pi/flood.py %d >/dev/null 2>&1 & sleep 0.3; "
           "cd ~ && python3 capture_csi.py %d /home/pi/capturas/%s"
           ) % (int(dur_csi + 1), int(dur_csi), SESSION)
    r = subprocess.run(["ssh", "-o", "ConnectTimeout=10", PI, cmd],
                       capture_output=True, text=True)
    result["csi"] = r.stdout[-400:] + r.stderr[-200:]

def run_kinect():
    r = subprocess.run(
        ["python", os.path.join(KINECT_DIR, "kinect_capture_pointcloud.py"),
         "--out-dir", os.path.join(OUT, "kinect"),
         "--duration", str(DUR), "--fps-target", "10", "--num-points", "1200",
         "--min-range", "0.4", "--max-range", "2.5", "--save-ply-every", "10"],
        cwd=KINECT_DIR, env=env, capture_output=True, text=True)
    result["kinect"] = r.stdout[-500:] + r.stderr[-300:]

print(">> Sesion:", SESSION, "| duracion:", DUR, "s | offset PC<->Pi:",
      ("%.1f ms" % (offset*1000)) if offset is not None else "DESCONOCIDO")
print(">> Lanzando Kinect (PC) + CSI (Pi) simultaneamente...")

t_csi = threading.Thread(target=run_csi)
t_kin = threading.Thread(target=run_kinect)
t_csi.start(); t_kin.start()
t_csi.join(); t_kin.join()

print("\n--- Kinect ---\n", result.get("kinect", "(sin salida)"))
print("\n--- CSI (Pi) ---\n", result.get("csi", "(sin salida)"))

print(">> Trayendo CSI del Pi a la PC...")
csi_dir = os.path.join(OUT, "csi")
os.makedirs(csi_dir, exist_ok=True)
# copia los rx*.csv DIRECTO a OUT/csi/ (sin carpeta anidada). El shell remoto expande el glob.
subprocess.run("scp -o ConnectTimeout=10 \"%s:/home/pi/capturas/%s/rx*.csv\" \"%s\""
               % (PI, SESSION, csi_dir), shell=True)

print("\n>> LISTO. Sesion guardada en:", OUT)
print("   kinect/  (nubes .bin + timestamps.csv, reloj PC)")
print("   csi/     (rx*.csv con seq, reloj Pi)")
print("   offset_pc_pi.txt")
print(">> Ahora corre:  python emparejar.py \"%s\"" % OUT)
