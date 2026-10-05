# Entrenar el modelo (un solo paso)

Guía para entrenar el modelo **CSI2PointCloud** con las **6 clases** capturadas, pensada para la
**PC de la universidad** (mejores componentes / GPU). El dataset ya está en formato MM-Fi.

---

## Qué se entrena

Un **transformer CSI2PointCloud** (arquitectura de Määttä et al.) que recibe el **CSI de Wi-Fi**
(amplitud + fase, 3 receptores × 114 subportadoras × ventana de 10) y predice la **nube de puntos 3D
del cuerpo** (1200 puntos). Se entrena con la pérdida **Chamfer + regularización**.

- **Datos:** `mmfi_dataset/E01/S01/A01…A06` — 6 clases, ~700 pares (CSI ↔ nube).
- **Split:** 70 % train / 15 % val / 15 % test, **cronológico por acción** (sin fuga temporal).
- **Salida:** `resultados/modelo/csi2pc_v2.pth`, curvas, visualización GT vs predicho y métricas ICP.

---

## Requisitos previos (una sola vez)

1. **Python 3.10+** instalado.
2. **Instalar librerías:**
   ```bash
   pip install -r requirements.txt
   ```

> **Todo lo demás ya viene en el repo:** el **dataset** (`mmfi_dataset/`, 6 clases), el **modelo de
> Määttä** (`csi2pointcloud/`, MIT) y las **capturas crudas** de respaldo. No hace falta clonar ni
> descargar nada más.

**Rutas (opcional):** los scripts toman por defecto el modelo y el dataset de dentro del repo. Solo
define estas variables si usas otras ubicaciones:
- `CSI2PC_REPO` → carpeta del modelo (por defecto: `csi2pointcloud/` dentro del repo).
- `CSI2PC_DATA` → dataset (por defecto: `mmfi_dataset/` dentro del repo).
- `CSI2PC_OUT`  → resultados (por defecto `pc/resultados/`).

---

## Entrenar con un solo botón

### Windows
Doble clic en **`entrenar_universidad.bat`** (o ejecútalo en una terminal).
Hace todo de corrido: entrena (60 épocas) → saca métricas de test → genera la visualización.

### Linux / macOS
```bash
bash entrenar_universidad.sh
```

### Opción Jupyter (dos notebooks: entrenar y test)
Si prefieres ver el proceso **paso a paso** de forma interactiva:
```bash
jupyter lab
```
1. Abre **`pc/entrenar.ipynb`** → Run All → entrena (split 70/15/15) y guarda
   `modelo/csi2pc_v2.pth` + `split.json`.
2. Abre **`pc/test.ipynb`** → Run All → carga ese modelo, saca las **métricas ICP** (fitness,
   RMSE, Chamfer) sobre el test y muestra la **visualización GT vs predicho** (colores de Määttä).

Ambos scripts ejecutan, en orden:
```bash
python pc/entrenar_v2.py 60     # entrena (split 70/15/15 por acción) y guarda el mejor modelo por val
python pc/test.py               # métricas ICP (fitness, RMSE, Chamfer) sobre el test reservado
python pc/vis_matta.py          # imagen GT vs predicho con colores de Määttä
```

> Si la PC tiene **GPU NVIDIA**, instala la build de PyTorch con CUDA (ver [requirements.txt](requirements.txt))
> y el entrenamiento usará la GPU automáticamente (mucho más rápido que en CPU).

---

## Qué revisar al terminar

En la carpeta de resultados:
- **`curva_perdida.png`** — pérdida train/val por época (debe bajar y no separarse → sin overfitting).
- **`pred_vs_gt.png`** — nube real (Kinect) vs predicha (IA), **colores de Määttä**.
- **`metricas_test.txt`** — ICP fitness, ICP RMSE y Chamfer, global y por acción.
- **`modelo/csi2pc_v2.pth`** — el modelo entrenado (mejor época según validación).

Para animaciones o un frame puntual:
```bash
python pc/vis_matta.py A03 10    # una acción y frame concretos
python pc/video_pred.py          # GIF recorriendo frames
```

---

## Ajustes útiles
- Más/menos épocas: `python pc/entrenar_v2.py 100`.
- Umbral de la métrica ICP (metros): `python pc/test.py 0.05`.
- El split (70/15/15) se fija en `pc/entrenar_v2.py` (variable `SPLIT`) y queda registrado en
  `resultados/split.json`, que `test.py` reutiliza para evaluar exactamente el mismo test.
