# -*- coding: utf-8 -*-
"""
Ejecuta el pipeline completo desde cero y, opcionalmente, los experimentos de
comparacion. Todo se SOBRESCRIBE: cada notebook escribe en rutas fijas dentro
de su carpeta de salida.

Pipeline base (sobrescribe pc/resultados/):
    python pc/correr_todo.py

Pipeline base + los dos experimentos de comparacion para la tesis:
    python pc/correr_todo.py --experimentos

Solo una etapa:
    python pc/correr_todo.py --solo eda
    python pc/correr_todo.py --solo entrenar
    python pc/correr_todo.py --solo test

Cada notebook se ejecuta con kernel limpio (nbconvert --execute), asi que no hay
estado residual de ejecuciones anteriores: equivale a "Restart Kernel and Run All".
Las salidas quedan guardadas DENTRO del .ipynb (--inplace), de modo que las
figuras y los prints son los de esta corrida.

Requiere, ademas de las dependencias del modelo (requirements.txt: torch, open3d...):
    pip install nbconvert nbclient ipykernel platformdirs

Este script corre los NOTEBOOKS de tesis/, que son la unica via de
entrenamiento del repo.

Videos/GIF que SI se generan aqui (los hace test_tesis.ipynb):
    video_test_completo.mp4   todas las acciones del test
    video_test_<ACCION>.mp4   una accion (ACCION_GIF en el notebook)
    video_test_<ACCION>.gif   la misma, en GIF
Para un GIF por accion (gif_A01..A06) usa pc/gifs_por_accion.py.
"""
import argparse
import os
import subprocess
import sys
import time

AQUI  = os.path.dirname(os.path.abspath(__file__))
TESIS = os.path.abspath(os.path.join(AQUI, ".."))
SCR   = os.path.join(TESIS, "tesis")   # los 3 notebooks viven aqui
DATA  = os.path.join(TESIS, "mmfi_dataset")

# Orden obligatorio: entrenar escribe el .pth y el split.json que test necesita.
ETAPAS = [
    ("eda",      "eda_senal.ipynb",      "EDA de la senal (verifica la extraccion CSI)"),
    ("entrenar", "entrenar_tesis.ipynb", "Entrenamiento (sobrescribe modelo/csi2pc_v2.pth)"),
    ("test",     "test_tesis.ipynb",     "Evaluacion ICP + videos"),
]

# Experimentos de comparacion para la tesis. Cada uno entrena y evalua en su
# propia carpeta, sin tocar pc/resultados/.
#
# NOTA: la comparacion de data augmentation NO esta aqui. Las funciones existen
# en el repo original de Maata (augment_csi_data, create_augmented_dataset)
# pero el notebook no las usa, asi que activarla requiere modificar su
# dataloader, no solo una variable de entorno.
EXPERIMENTOS = [
    ("512", "resultados_512",
     {"CSI2PC_PRESET": "paper"},
     "Arquitectura del paper (embedding 512, 4+4 capas) vs la oficial (256, 3+3)"),
]


def correr_notebook(nb, out_dir, extra_env=None, timeout=7200):
    """Ejecuta un notebook con kernel limpio. Devuelve True si termino bien."""
    env = dict(os.environ)
    env["CSI2PC_DATA"] = DATA
    env["CSI2PC_OUT"]  = out_dir
    if extra_env:
        env.update(extra_env)

    os.makedirs(out_dir, exist_ok=True)
    cmd = [sys.executable, "-m", "nbconvert", "--to", "notebook", "--execute",
           "--inplace", "--ExecutePreprocessor.timeout=%d" % timeout, nb]

    t0 = time.time()
    # cwd = tesis/ porque los notebooks resuelven sus rutas desde os.getcwd()
    r = subprocess.run(cmd, cwd=SCR, env=env)
    dt = time.time() - t0
    print("    -> %s en %.1f s" % ("OK" if r.returncode == 0 else "FALLO", dt))
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", choices=[e[0] for e in ETAPAS],
                    help="ejecuta una sola etapa del pipeline base")
    ap.add_argument("--experimentos", action="store_true",
                    help="tras el pipeline base, corre la comparacion de arquitectura 512")
    args = ap.parse_args()

    if not os.path.isdir(DATA):
        sys.exit("No existe %s. Genera el dataset con pc/formatear_mmfi_ma.py" % DATA)

    # Comprobar dependencias antes de empezar: mejor fallar aqui que a mitad
    # de un entrenamiento de 50 epocas.
    faltan = []
    for mod, paquete in [("nbclient", "nbclient"), ("nbconvert", "nbconvert"),
                         ("ipykernel", "ipykernel"), ("platformdirs", "platformdirs"),
                         ("torch", "torch (ver requirements.txt)"),
                         ("open3d", "open3d")]:
        try:
            __import__(mod)
        except ImportError:
            faltan.append(paquete)
    if faltan:
        sys.exit("Faltan dependencias en %s:\n  %s\n\nInstala con:\n  pip install %s"
                 % (sys.executable, "\n  ".join(faltan),
                    " ".join(p.split()[0] for p in faltan)))

    base_out = os.path.join(TESIS, "pc", "resultados")
    etapas = [e for e in ETAPAS if args.solo is None or e[0] == args.solo]

    print("Datos : %s" % DATA)
    print("Salida: %s" % base_out)
    print("Etapas: %s\n" % ", ".join(e[0] for e in etapas))

    for i, (clave, nb, desc) in enumerate(etapas, 1):
        print("[%d/%d] %s" % (i, len(etapas), desc))
        print("    %s" % nb)
        if not correr_notebook(os.path.join(SCR, nb), base_out):
            sys.exit("Fallo en '%s'. Se detiene aqui: las etapas siguientes "
                     "dependen de su salida." % clave)

    if args.experimentos:
        print("\n=== Experimentos de comparacion ===")
        print("Cada uno reentrena desde cero en su propia carpeta.\n")
        for clave, carpeta, env, desc in EXPERIMENTOS:
            out = os.path.join(TESIS, "pc", carpeta)
            print("[%s] %s" % (clave, desc))
            print("    salida: %s" % out)
            ok = correr_notebook(os.path.join(SCR, "entrenar_tesis.ipynb"), out, env)
            if ok:
                correr_notebook(os.path.join(SCR, "test_tesis.ipynb"), out, env)
            else:
                print("    se omite la evaluacion de '%s'" % clave)

    print("\nListo. Resultados en %s" % base_out)


if __name__ == "__main__":
    main()
