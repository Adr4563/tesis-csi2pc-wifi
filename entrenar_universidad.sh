#!/usr/bin/env bash
# ============================================================
#  Entrenamiento del modelo CSI2PointCloud (6 clases) - 1 paso
#  Ejecuta: entrenar -> evaluar (test) -> visualizar.
# ============================================================
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"

# --- Ajustar estas rutas en la PC de la universidad si hace falta ---
export CSI2PC_REPO="${CSI2PC_REPO:-$HERE/../csi2pointcloud}"
export CSI2PC_DATA="${CSI2PC_DATA:-$HERE/../mmfi_dataset}"
export CSI2PC_OUT="${CSI2PC_OUT:-$HERE/pc/resultados}"

echo "============================================================"
echo " REPO modelo : $CSI2PC_REPO"
echo " DATOS       : $CSI2PC_DATA"
echo " RESULTADOS  : $CSI2PC_OUT"
echo "============================================================"

echo; echo "[1/3] Entrenando (60 epocas, split 70/15/15 por accion)..."
python "$HERE/pc/entrenar_v2.py" 60

echo; echo "[2/3] Metricas ICP sobre el TEST..."
python "$HERE/pc/test.py"

echo; echo "[3/3] Visualizacion GT vs predicho (colores de Maata)..."
python "$HERE/pc/vis_matta.py"

echo; echo "============================================================"
echo " LISTO. Resultados en: $CSI2PC_OUT"
echo "   - curva_perdida.png  - pred_vs_gt.png"
echo "   - metricas_test.txt  - modelo/csi2pc_v2.pth"
echo "============================================================"
