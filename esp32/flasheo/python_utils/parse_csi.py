import argparse
import re
from math import sqrt, atan2

import numpy as np


def parse_csi_file(csv_path):
    """
    Lee un CSV de captura del ESP32-CSI-Tool (con o sin host_timestamp
    apendeado por serial_append_time.py) y devuelve, por cada fila valida:
    timestamps, amplitude, phase (listas; cada elemento puede tener distinto
    largo si el numero de subcarriers vario entre paquetes).
    """
    timestamps = []
    amplitudes = []
    phases = []
    n_skipped = 0

    with open(csv_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("CSI_DATA"):
                continue  # header o linea vacia/corrupta

            if "[" not in line or "]" not in line:
                n_skipped += 1
                continue

            bracket_start = line.index("[")
            bracket_end = line.index("]")
            array_str = line[bracket_start + 1:bracket_end]
            suffix = line[bracket_end + 1:].lstrip(",").strip()

            try:
                csi_raw = [int(x) for x in array_str.split(" ") if x != ""]
            except ValueError:
                n_skipped += 1
                continue

            if len(csi_raw) < 2:
                n_skipped += 1
                continue

            # host_timestamp solo esta presente si el CSV paso por
            # serial_append_time.py (formato "...],1784310575.575"). Si no
            # esta, se guarda NaN y hay que alinear por orden/otro medio.
            host_timestamp = float(suffix) if suffix else float("nan")

            imaginary = csi_raw[0::2]
            real = csi_raw[1::2]

            amplitude = [sqrt(i ** 2 + r ** 2) for i, r in zip(imaginary, real)]
            phase = [atan2(i, r) for i, r in zip(imaginary, real)]

            timestamps.append(host_timestamp)
            amplitudes.append(amplitude)
            phases.append(phase)

    return timestamps, amplitudes, phases, n_skipped


def save_parsed(out_path, timestamps, amplitudes, phases):
    """
    Guarda el resultado en un .npz cargable despues con np.load(..., allow_pickle=True).
    Si todas las filas tienen el mismo numero de subcarriers, amplitude/phase
    quedan como arrays 2D (n_frames, n_subcarriers); si no, quedan como
    arrays de objeto (uno por fila, largo variable) y se avisa por consola.
    """
    lengths = {len(a) for a in amplitudes}
    if len(lengths) == 1:
        amplitude_arr = np.asarray(amplitudes, dtype=np.float64)
        phase_arr = np.asarray(phases, dtype=np.float64)
    else:
        print(f"  [!] Los paquetes tienen distinto numero de subcarriers ({sorted(lengths)}); "
              f"se guarda como array de largo variable (dtype=object).")
        amplitude_arr = np.array(amplitudes, dtype=object)
        phase_arr = np.array(phases, dtype=object)

    np.savez(
        out_path,
        timestamp=np.asarray(timestamps, dtype=np.float64),
        amplitude=amplitude_arr,
        phase=phase_arr,
    )


def main():
    parser = argparse.ArgumentParser(description="Convierte CSI cruda (I/Q) del ESP32-CSI-Tool a amplitud/fase.")
    parser.add_argument("csv_path", nargs="?", default="./example_csi.csv", help="CSV de entrada (capturado con serial_append_time.py). Por defecto example_csi.csv.")
    parser.add_argument("--out", type=str, default=None, help="Ruta del .npz de salida. Por defecto: mismo nombre que el CSV con extension .npz.")
    args = parser.parse_args()

    out_path = args.out or re.sub(r"\.csv$", "", args.csv_path) + "_parsed.npz"

    timestamps, amplitudes, phases, n_skipped = parse_csi_file(args.csv_path)

    if not amplitudes:
        print(f"No se encontraron filas CSI_DATA validas en '{args.csv_path}'.")
        return

    save_parsed(out_path, timestamps, amplitudes, phases)

    n_no_ts = sum(1 for t in timestamps if t != t)  # cuenta NaN
    print(f">> {len(amplitudes)} paquetes CSI procesados ({n_skipped} filas invalidas descartadas) -> '{out_path}'")
    if n_no_ts > 0:
        print(f"  [!] {n_no_ts} de {len(amplitudes)} filas no tenian host_timestamp "
              f"(CSV sin pasar por serial_append_time.py) -> quedaron como NaN.")


if __name__ == "__main__":
    main()
