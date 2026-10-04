# -*- coding: utf-8 -*-
"""
Captura GUIADA de las 7 clases (estatico + 6 acciones) en formato MM-Fi.
Por cada accion: resetea los ESP32 -> cuenta regresiva -> captura sincronizada
(Kinect + CSI) -> empareja -> formatea a MM-Fi con la etiqueta A## correcta.

Uso:
  python capturar_acciones.py            -> hace TODAS las acciones en orden
  python capturar_acciones.py A03        -> solo esa accion (re-captura)
  python capturar_acciones.py A03 A05    -> esas acciones
  python capturar_acciones.py --dur 40   -> cambia duracion (default 30s)
"""
import subprocess, sys, time, os

PI      = "pi@192.168.0.179"
LAPTOP  = "192.168.0.75"
HERE    = os.path.dirname(os.path.abspath(__file__))
BASE    = r"C:\Users\user\Desktop\Carpeta_Trabajo\capturas_sync"
SCENE, SUBJECT, MA_WIN = "E01", "S01", "5"

ACCIONES = [
    ("A01", "ESTATICO: parate quieto, de pie, mirando a la camara"),
    ("A02", "BRAZOS ARRIBA: sube y baja los brazos lentamente"),
    ("A03", "CAMINAR EN EL SITIO: marcha sin avanzar"),
    ("A04", "AGACHARSE: agachate y levantate repetidamente"),
    ("A05", "GIRAR TORSO: gira el torso a izquierda y derecha"),
    ("A06", "SENTARSE/PARARSE: sientate y parate (usa una silla)"),
    ("A07", "ESTIRAR PIERNAS: levanta una pierna y luego la otra"),
]

DUR = 30.0
PREP = 3          # segundos de aviso antes de cada captura (en vez de ENTER)
args = sys.argv[1:]
if "--dur" in args:
    i = args.index("--dur"); DUR = float(args[i + 1]); del args[i:i + 2]
if "--prep" in args:
    i = args.index("--prep"); PREP = int(args[i + 1]); del args[i:i + 2]
sel = [a.upper() for a in args] if args else None
lista = [(a, d) for a, d in ACCIONES if (sel is None or a in sel)]


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def reset_esp32():
    """Pulso EN para sacar los ESP32 del bootloader ROM (vienen del cuelgue por power)."""
    py = (
        "python3 -c \"import serial,time\n"
        "for p in ['/dev/ttyACM0','/dev/ttyACM1','/dev/ttyACM2']:\n"
        "    try:\n"
        "        s=serial.Serial(); s.port=p; s.baudrate=115200; s.dtr=False; s.rts=False; s.open();"
        " s.dtr=True; time.sleep(0.1); s.dtr=False; s.close()\n"
        "    except Exception as e: print(p,'err',e)\""
    )
    sh('ssh -o ConnectTimeout=10 %s "%s"' % (PI, py))
    time.sleep(4)


def laptop_ok():
    """La laptop debe estar ASOCIADA al WiFi (aunque no responda ping) para generar trafico."""
    r = sh('ssh -o ConnectTimeout=8 %s "arp -n %s 2>/dev/null; iw dev 2>/dev/null | grep -c Interface"' % (PI, LAPTOP))
    return True  # informativo; la asociacion la confirma el conteo de CSI


def countdown(n):
    for k in range(n, 0, -1):
        print("   %d..." % k, flush=True); time.sleep(1)


def una_accion(a, desc):
    sesion = "acc_%s" % a
    # limpiar sesion previa (evita rx*.csv vacios de intentos fallidos)
    import shutil
    prev = os.path.join(BASE, sesion)
    if os.path.isdir(prev):
        shutil.rmtree(prev, ignore_errors=True)
    print("\n" + "=" * 60)
    print(">> ACCION %s" % a)
    print(">> %s" % desc)
    print("=" * 60)
    print(">> Reseteando ESP32...", flush=True)
    reset_esp32()
    print(">> PONTE EN POSICION PARA: %s" % desc, flush=True)
    print(">> La captura inicia en:", flush=True); countdown(PREP)
    print(">> CAPTURANDO %.0fs - HAZ LA ACCION AHORA!" % DUR, flush=True)

    r = sh('cd /d "%s" && python captura_sincronizada.py %.0f %s' % (HERE, DUR, sesion))
    print(r.stdout[-600:] if r.stdout else r.stderr[-600:], flush=True)

    sesion_path = os.path.join(BASE, sesion)
    print(">> Emparejando...", flush=True)
    r = sh('cd /d "%s" && python emparejar.py "%s"' % (HERE, sesion_path))
    print(r.stdout[-300:], flush=True)

    # limpiar carpeta destino A## para no mezclar frames de capturas previas
    dst = os.path.join(BASE, "mmfi_dataset", SCENE, SUBJECT, a)
    if os.path.isdir(dst):
        import shutil; shutil.rmtree(dst, ignore_errors=True)
        print(">> Carpeta %s limpiada (evita frames viejos mezclados)" % a, flush=True)

    print(">> Formateando a MM-Fi (%s)..." % a, flush=True)
    r = sh('cd /d "%s" && python formatear_mmfi_ma.py "%s" %s %s %s %s'
           % (HERE, sesion_path, SCENE, SUBJECT, a, MA_WIN))
    print(r.stdout[-300:], flush=True)
    print(">> LISTO accion %s\n" % a, flush=True)


if __name__ == "__main__":
    print(">> Capturare: %s | duracion %.0fs c/u" % (", ".join(a for a, _ in lista), DUR))
    for a, desc in lista:
        una_accion(a, desc)
    print("\n>> TODAS LISTAS. Dataset MM-Fi actualizado en:")
    print("   %s\\mmfi_dataset\\%s\\%s\\" % (BASE, SCENE, SUBJECT))
    print(">> Ahora se puede entrenar con las 7 clases.")
