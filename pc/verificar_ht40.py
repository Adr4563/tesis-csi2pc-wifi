# -*- coding: utf-8 -*-
"""
verificar_ht40.py  -  Verificacion REPRODUCIBLE y NEUTRAL de la extraccion HT40 del CSI.

NO asume que la extraccion es correcta: mide los datos crudos y REPORTA lo que encuentra
(incluye alertas si algo no cuadra, p.ej. valores no nulos en el hueco DC central, o
bloques de senal en indices distintos a los esperados).

Lo que verifica, a partir de los rx*.csv crudos:
  - longitud de los paquetes (384 = HT40 / 256 = HT20 / otro)
  - magnitud media por indice crudo 0..191 y los BLOQUES con senal (deteccion automatica)
  - el hueco DC/guarda central: reporta su magnitud (deberia ser ~0; ALERTA si no)
  - la costura del concatenado [66:123]+[134:191]

Uso:  python verificar_ht40.py <carpeta_csi>  [n_paquetes]
      python verificar_ht40.py ../capturas_crudas/sesion2_estatica/csi  300
"""
import sys, os, glob, ast
import numpy as np

CSI_DIR = sys.argv[1] if len(sys.argv) > 1 else "../capturas_crudas/sesion2_estatica/csi"
NMAX    = int(sys.argv[2]) if len(sys.argv) > 2 else 300
UMBRAL  = 1.0   # magnitud media por encima de la cual se considera "con senal"


def parse_line(line):
    if "CSI_DATA" not in line:
        return None
    try:
        return ast.literal_eval(line[line.index("["):line.rindex("]") + 1])
    except Exception:
        return None


def analizar(path):
    lens, mags = {}, []
    corruptos = 0
    for line in open(path, encoding="utf-8", errors="ignore"):
        arr = parse_line(line)
        if arr is None:
            if "CSI_DATA" in line:
                corruptos += 1
            continue
        lens[len(arr)] = lens.get(len(arr), 0) + 1
        if len(arr) == 384 and len(mags) < NMAX:
            a = np.array(arr, float)
            mags.append(np.abs(a[1::2] + 1j * a[0::2]))   # 192 complejos
    return lens, (np.mean(mags, 0) if mags else None), corruptos, len(mags)


def bloques_no_cero(M, umbral):
    nz = np.where(M > umbral)[0]
    if len(nz) == 0:
        return []
    bl, ini, prev = [], nz[0], nz[0]
    for i in nz[1:]:
        if i != prev + 1:
            bl.append((int(ini), int(prev))); ini = i
        prev = i
    bl.append((int(ini), int(prev)))
    return bl


def main():
    files = sorted(glob.glob(os.path.join(CSI_DIR, "rx*.csv")))
    if not files:
        print("No hay rx*.csv en", CSI_DIR); return
    print("=" * 64)
    print("VERIFICACION HT40 |", CSI_DIR)
    print("=" * 64)
    ESPERADOS = [(66, 122), (134, 190)]   # bloques HT-LTF esperados (hipotesis a comprobar)

    for f in files:
        lens, M, corruptos, n384 = analizar(f)
        print("\n[%s]" % os.path.basename(f))
        print("  longitudes de paquete:", dict(sorted(lens.items())), "| corruptos:", corruptos)
        if 384 not in lens:
            print("  ALERTA: no hay paquetes HT40 (len=384). No se puede verificar la extraccion.")
            continue
        if M is None:
            print("  ALERTA: no se pudieron promediar paquetes 384."); continue

        bl = bloques_no_cero(M, UMBRAL)
        print("  paquetes HT40 analizados:", n384)
        print("  bloques con senal (indice 0..191):", bl)

        # verificacion NEUTRAL de los bloques HT-LTF esperados
        htltf = [b for b in bl if b[1] - b[0] >= 50]   # bloques "grandes" (~57)
        ok_bloques = sorted(htltf) == ESPERADOS
        print("  bloques HT-LTF (>=50 subp):", htltf,
              "-> coinciden con %s?" % str(ESPERADOS), "SI" if ok_bloques else "NO (revisar)")

        # hueco DC central 123..133: deberia ser ~0
        dc = M[123:134]
        print("  hueco DC central (123..133): magnitud media = %.3f, max = %.3f" % (dc.mean(), dc.max()),
              "-> OK (nulo)" if dc.max() < UMBRAL else "-> ALERTA: hay senal en el hueco DC")

        # costura del concatenado
        if ok_bloques:
            c = np.concatenate([M[66:123], M[134:191]])
            print("  concatenado = %d subportadoras" % len(c),
                  "-> OK (114)" if len(c) == 114 else "-> ALERTA (no 114)")
            print("  costura subp 57: %.1f (idx122) -> %.1f (idx134) | salto = %.1f"
                  % (M[122], M[134], abs(M[134] - M[122])))

    print("\n" + "=" * 64)
    print("NOTA: este script REPORTA lo medido. 'coinciden? SI' solo confirma que los")
    print("bloques de senal estan donde la extraccion asume. El mapeo exacto")
    print("indice->frecuencia de cada subportadora NO se valida aqui (ver verificacion_ht40.md).")


if __name__ == "__main__":
    main()
