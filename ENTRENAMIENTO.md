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
> Määttä** (`tesis/modelo/`, MIT) y las **capturas crudas** de respaldo. No hace falta clonar ni
> descargar nada más.

**Rutas (opcional):** los scripts toman por defecto el modelo y el dataset de dentro del repo. Solo
define estas variables si usas otras ubicaciones:
- El modelo se importa desde `tesis/modelo/` (ya no hace falta `CSI2PC_REPO`).
- `CSI2PC_DATA` → dataset (por defecto: `mmfi_dataset/` dentro del repo).
- `CSI2PC_OUT`  → resultados (por defecto `pc/resultados/`).

---

## Entrenar con un solo comando

```bash
python pc/correr_todo.py
```
Corre los 3 notebooks de `tesis/` en orden, cada uno con **kernel limpio**, y
sobrescribe `pc/resultados/`:

1. **`eda_senal.ipynb`** → figuras del EDA y control de calidad de la extraccion CSI.
2. **`entrenar_tesis.ipynb`** → entrena (50 épocas, split 70/15/15 por acción) y
   guarda `modelo/csi2pc_v2.pth` + `split.json`.
3. **`test_tesis.ipynb`** → carga ese modelo, saca las **métricas ICP** (fitness,
   RMSE, Chamfer) sobre el test y genera los vídeos GT vs predicho.

El orden importa: el test evalúa el `.pth` que escribe el entrenamiento.

Una sola etapa: `python pc/correr_todo.py --solo entrenar`.

### Opción interactiva
Abre los notebooks de **`tesis/`** en VSCode o Jupyter y usa
**Restart Kernel and Run All** en cada uno, en el mismo orden.

> Si la PC tiene **GPU NVIDIA**, instala la build de PyTorch con CUDA (ver [requirements.txt](requirements.txt))
> y el entrenamiento usará la GPU automáticamente (mucho más rápido que en CPU).

---

## Qué revisar al terminar

En la carpeta de resultados:
- **`curva_perdida.png`** — pérdida train/val por época (debe bajar y no separarse → sin overfitting).
- **`pred_vs_gt.png`** — nube real (Kinect) vs predicha (IA), **colores de Määttä**.
- **`metricas_test.txt`** — ICP fitness, ICP RMSE y Chamfer, global y por acción.
- **`modelo/csi2pc_v2.pth`** — el modelo entrenado (mejor época según validación).

Vídeos y GIF (los genera `test_tesis.ipynb`): `video_test_completo.mp4`,
`video_test_<ACCION>.mp4/.gif`.

Un GIF por cada acción:
```bash
python pc/gifs_por_accion.py          # las 6 acciones
python pc/gifs_por_accion.py A03 A05  # solo esas
```

---

## Ajustes útiles
- Épocas, batch, lr y arquitectura: diccionario `CFG` en `tesis/entrenar_tesis.ipynb`.
- Arquitectura del paper (512, 4+4) en vez de la oficial (256, 3+3):
  `CSI2PC_PRESET=paper`, o `python pc/correr_todo.py --experimentos`.
- Umbrales de la métrica ICP: lista `UMBRALES` en `tesis/test_tesis.ipynb`.
- El split (70/15/15 cronológico por acción) lo escribe el entrenamiento en
  `resultados/split.json`, y `test_tesis.ipynb` lo reutiliza para evaluar el mismo test.
