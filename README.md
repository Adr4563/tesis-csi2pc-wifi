# Reconstrucción de nubes de puntos 3D del cuerpo humano a partir de señales CSI de Wi-Fi

Proyecto de tesis — Universidad de Lima.
Extensión y validación, con hardware propio, del modelo **CSI2PointCloud** (Määttä et al., 2025,
*"Spatio-Temporal 3D Point Clouds from WiFi-CSI Data via Transformer Networks"*), entrenado
originalmente sobre el dataset **MM-Fi**.

El sistema capta **Channel State Information (CSI)** de Wi-Fi con sniffers ESP32-S3 y, en paralelo,
nubes de puntos 3D con una cámara **Azure Kinect**. Con esos pares (CSI ↔ nube) se entrena un
transformer que aprende a **reconstruir la nube de puntos del cuerpo humano usando solo el Wi-Fi**.

---

## 0. Inicio rápido — entrenar en otra PC (p. ej. la universidad)

> Este repo es **autónomo**: ya incluye el **dataset** (`mmfi_dataset/`, 6 clases), el **modelo de
> Määttä** (`csi2pointcloud/`, MIT) y las **capturas crudas** de respaldo. **No hace falta descargar
> nada más** (ni siquiera internet, salvo para instalar las librerías de Python).

**1) Clonar (o copiar) solo este repo:**
```bash
git clone https://github.com/Adr4563/tesis-csi2pc-wifi
cd tesis-csi2pc-wifi
```
Estructura (todo ya viene dentro):
```
  tesis-csi2pc-wifi/
  ├── mmfi_dataset/     ← datos (CSI + Kinect, 6 clases)
  ├── csi2pointcloud/   ← modelo de Maata (incluido, MIT)
  ├── capturas_crudas/  ← respaldo de las capturas crudas
  ├── pc/  pi/  kinect/  esp32/  docs/
  └── entrenar_universidad.bat / .sh
```

**2) Instalar librerías** (se recomienda un entorno virtual; con GPU, ver [requirements.txt](requirements.txt)):
```bash
pip install -r requirements.txt
```

**3) Entrenar con un solo paso:**
- **Windows:** doble clic en `entrenar_universidad.bat`
- **Linux/macOS:** `bash entrenar_universidad.sh`

Eso entrena (40 épocas, igual que Määttä) → saca métricas ICP del test → genera la visualización. Resultados en
`pc/resultados/`. Detalle en [`ENTRENAMIENTO.md`](ENTRENAMIENTO.md).

> El modelo y el dataset se toman por defecto de dentro del repo. Para usar otros, define las
> variables `CSI2PC_REPO` / `CSI2PC_DATA` antes de entrenar.

---

## 1. Idea general del pipeline

```
   Router Wi-Fi (TX)                 Azure Kinect (PC)
        │  transmite al aire               │ nubes de puntos 3D
        ▼                                   ▼
   3 ESP32-S3 (sniffers) ── USB ──► Raspberry Pi ──(CSI, reloj Pi)
                                          │
                                          │ scp
                                          ▼
                                     PC (Windows)
                      empareja CSI ↔ nube por tiempo  →  formato MM-Fi
                                          │
                                          ▼
                       Transformer CSI2PointCloud (entrenamiento local)
                                          │
                                          ▼
                     Nube de puntos predicha SOLO con Wi-Fi + métricas ICP
```

---

## 2. Entorno de trabajo (software)

| Componente | Sistema / versión |
|---|---|
| **PC principal** | Windows 10 Pro (64-bit) — captura Kinect, emparejado, formato, **entrenamiento** |
| **Raspberry Pi** | Raspberry Pi OS (Linux) — lee los 3 ESP32 por USB y genera el tráfico |
| **ESP32-S3 ×3** | Firmware ESP-IDF (proyecto `esp-csi`, ejemplo `csi_recv` en modo sniffer) |
| **Python** | 3.10+ (PC y Pi) |
| **Modelo** | PyTorch (CPU en este trabajo; GPU opcional en la universidad) |

> Se trabaja en **dos sistemas operativos a la vez**: la **Raspberry corre Linux** (acceso cómodo a
> los `/dev/ttyACM*` de los ESP32 y a `ping`/`sudo` para el tráfico) y la **PC corre Windows**
> (SDK de Azure Kinect + entrenamiento). La comunicación PC↔Pi es por **SSH/SCP** sobre la misma red.

### Librerías principales
- **PyTorch** — modelo transformer CSI2PointCloud y entrenamiento.
- **Open3D** — nubes de puntos, registro **ICP**, auto-nivelado del piso, visores 3D.
- **NumPy / SciPy** — procesamiento del CSI (`scipy.io` para `.mat`), álgebra.
- **Matplotlib** — curvas de pérdida y visualización GT vs predicho.
- **pyserial** — lectura de los ESP32 por UART/USB en la Raspberry.
- **pyk4a** — acceso a la Azure Kinect desde Python (requiere el *Azure Kinect SDK v1.4.1*).
- **Pillow** — generación del GIF animado de resultados.

Instalación: ver [`requirements.txt`](requirements.txt).

---

## 3. Distribución espacial de los componentes

Coordenadas en el piso en **centímetros** `(x, y)`, vista en planta. Alturas medidas aparte.

```
   y(cm)
   258 ┤                      ● Cámara Azure Kinect  (140, 258)  h=117 cm
   250 ┤                      ▣ Router Wi-Fi (TX)    (140, 250)  h=73 cm
       │
   140 ┤ ● Laptop (cliente)                           (0, 140)
       │   (genera el tráfico de destino)
   100 ┤                   ☺ SUJETO                   (~100, 100)
       │
     0 ┤                      ▣ 3×ESP32-S3 + Raspberry Pi  (150, 0)
       └┬─────────┬──────────┬──────────┬─────────► x(cm)
        0        50         100        150
```

- **Cámara Azure Kinect:** `(140, 258)`, **altura 117 cm**, apuntando de frente al sujeto.
- **Router Wi-Fi (TP-Link Archer AX53):** `(140, 250)`, **altura 73 cm**. Es el **transmisor (TX)**.
- **3× ESP32-S3 + Raspberry Pi:** `(150, 0)` — los sniffers están juntos en el mismo punto
  (receptores RX; solo escuchan).
- **Laptop:** `(0, 140)` — cliente Wi-Fi que sirve de **destino del tráfico** (ver §6).
- **Sujeto:** aprox. `(100, 100)`, **de pie, de frente a la cámara**, a ~1–2 m de la Kinect.

**Distancia de captura:** el sujeto se ubica dentro del rango útil de la Kinect
(**0.4 m – 2.5 m**); en estas tomas, ~**1 a 2 metros** de la cámara. La cámara queda **detrás**
de los receptores, mirando al sujeto de frente, para que la nube salga derecha (no diagonal).

> La cámara se **auto-nivela por software** (detección del plano del piso con RANSAC y rotación a
> la horizontal) para corregir cualquier inclinación de montaje.

---

## 4. Hardware y su rol

| Elemento | Rol | Nota |
|---|---|---|
| **Router TP-Link Archer AX53** | **TX** — transmite al aire | 2.4 GHz, canal 6, ancho 40 MHz (HT40) |
| **3× ESP32-S3** | **RX** — sniffers de CSI | Solo escuchan; filtran por la MAC del router |
| **Raspberry Pi** | Orquesta los RX + genera tráfico | Lee los 3 ESP32 por USB, pone marca de tiempo |
| **Laptop** | Cliente Wi-Fi (destino del tráfico) | Debe estar **asociada** al router (ver §6) |
| **PC (Windows)** | Kinect + entrenamiento | Azure Kinect SDK + PyTorch |
| **Azure Kinect** | Ground-truth (nubes 3D) | ToF, un solo punto de vista |

---

## 5. Configuración de cada parte

### 5.1 Router (TP-Link Archer AX53)
- Banda **2.4 GHz**, **Canal 6**, **Ancho de canal 40 MHz** (necesario para HT40 / 114 subportadoras).
- Modo: `802.11b/g/n/ax mixed` (es el modo con el que el enlace de la Pi queda estable).
- OFDMA / TWT / Smart Connect: **desactivados**.

### 5.2 Raspberry Pi
- Raspberry Pi OS. Los 3 ESP32 aparecen como `/dev/ttyACM0/1/2` (driver CDC-ACM; chip CH343).
- `sudo` sin contraseña para `ping` (necesario para generar el tráfico desde scripts).
- Scripts en `/home/pi/`: [`pi/capture_csi.py`](pi/capture_csi.py), [`pi/flood.py`](pi/flood.py).

### 5.3 ESP32-S3 (firmware)
Ver [`esp32/CONFIG.md`](esp32/CONFIG.md). Puntos clave:
- Ejemplo `csi_recv` del proyecto `esp-csi`, en **modo sniffer (promiscuo)**.
- `CONFIG_ESP_CONSOLE_UART_BAUDRATE = 4000000` (4 Mbaud, para no saturar el serial a ~100 muestras/s).
- Canal **6** (igual que el router).
- Filtro por la **MAC del router** (`3c:78:95:2b:86:2f`): solo se procesan tramas que vienen del router.
- HT40 (114 subportadoras), se añade el campo `rx_seq` (número de secuencia 802.11) a la salida
  para sincronización fina entre placas.

---

## 6. Envío de datos: cómo se logra ~100 CSI/s (y por qué la laptop es clave)

Este fue uno de los puntos críticos del proyecto. Resumen de lo aprendido y la solución final.

### El problema
Un ESP32 captura **una medición CSI por cada trama física (PPDU) que el router transmite al aire**,
**no** por cada paquete de datos. El router usa **agregación A-MPDU**: junta muchos paquetes en una
sola trama grande. Por eso, aunque se inunde la red con miles de paquetes UDP, el router los emite en
pocas tramas físicas → la tasa de CSI se estanca (~65/s con UDP).

### Por qué hace falta la laptop (y no basta con la Pi o la PC)
El sniffer solo ve lo que el router **transmite al aire hacia un cliente inalámbrico**.
- La **PC está por Ethernet** → el router no le transmite por aire; no sirve como destino.
- El **router no reenvía** tráfico "al aire hacia sí mismo"; hacerle ping da ~0 CSI útil.
- La **laptop está por Wi-Fi** → cuando la Raspberry le manda tráfico, **el router lo transmite al aire
  hacia la laptop**, y *esas* tramas (origen = MAC del router) son las que los ESP32 sniffean.

**Importante:** la laptop **no necesita responder** el tráfico. Basta con que esté **asociada al Wi-Fi
del router**; el solo hecho de que el router le transmita al aire genera el CSI. Por eso un `ping` que
marca "100% perdido" (firewall de la laptop) **igual produce CSI**, mientras la laptop siga conectada.

> Si la laptop se **cambia de red** o se desconecta, el flujo se cae a **0 CSI**. Verificar siempre que
> la laptop esté asociada a la red del Archer antes de capturar.

### La solución
Generar el tráfico con **ping ICMP a ritmo fijo desde la Raspberry hacia la laptop**
(ICMP se agrega mucho menos que un flood UDP → más PPDUs → más CSI):

```bash
sudo ping -i 0.006 -s 0 192.168.0.75   # ~166 paquetes/s -> ~95-97 CSI/s tras agregación
```

Esto es lo que hace [`pi/flood.py`](pi/flood.py). Resultado: **~92–97 CSI/s estables** en las 3 placas,
suficiente para capturar al sujeto **en movimiento**.

> **Detalle completo** (PPDUs, A-MPDU, Mbps, comparativa UDP vs ICMP, límites de serial y
> alimentación, sincronización): ver [`docs/RED_Y_TRAFICO.md`](docs/RED_Y_TRAFICO.md).

### Estabilidad eléctrica (caídas de los ESP32)
Con los 3 ESP32-S3 transmitiendo a ~100/s, el consumo supera lo que entregan los puertos USB de la Pi
→ **brownout**: las placas se **desconectan del bus USB** o se **reinician al bootloader ROM** y dejan
de sniffear (se ve en `dmesg` como `USB disconnect` o `error -71`, y al leer el puerto aparece
`ESP-ROM:esp32s3...`). **Solución:** alimentar los ESP32 con **más voltaje / un hub USB con alimentación
externa**. Con alimentación estable, las 3 placas se mantienen clavadas en ~92–95/s sin caerse.
Si una placa quedó en ROM, se la saca con un **pulso de reset por software** (toggle de la línea DTR):
el script [`pc/capturar_acciones.py`](pc/capturar_acciones.py) lo hace automáticamente antes de cada captura.

---

## 7. Formato de datos (MM-Fi)

Los pares se guardan en la estructura del dataset MM-Fi para ser compatibles con el modelo:

```
mmfi_dataset/
└── E01/                      escena
    └── S01/                  sujeto
        ├── A01/ ... A06/     acción
        │   ├── wifi-csi/frameNNN.mat   CSIamp[3,114,10], CSIphase[3,114,10]
        │   └── lidar/frameNNN.bin      nube 1200 puntos, float64 (x,y,z)
```

- **3** = antenas/receptores (los 3 ESP32), **114** = subportadoras HT40, **10** = ventana temporal.
- Preprocesamiento del CSI (igual que Määttä/MM-Fi): **media móvil** sobre el CSI complejo, luego
  amplitud normalizada min-max `[0,1]` + fase cruda; la nube se normaliza `(x-media)/std`.
- Clases capturadas en este trabajo (6): A01 estático, A02 brazos en cruz (abrir/cerrar),
  A03 caminar en el sitio, A04 agacharse, A05 girar torso, A06 estirar piernas.

---

## 8. Comandos — de principio a fin

### 8.1 Arrancar la Raspberry y verificar los ESP32
```bash
# desde la PC, entrar a la Pi
ssh pi@192.168.0.179

# ver que aparezcan los 3 sniffers
ls /dev/ttyACM*            # -> /dev/ttyACM0  /dev/ttyACM1  /dev/ttyACM2

# (si alguno quedó en bootloader ROM) resetearlos por software:
python3 - <<'PY'
import serial, time
for p in ['/dev/ttyACM0','/dev/ttyACM1','/dev/ttyACM2']:
    s = serial.Serial(); s.port = p; s.baudrate = 115200
    s.dtr = False; s.rts = False; s.open()
    s.dtr = True; time.sleep(0.12); s.dtr = False; s.close()
print("reset ok")
PY

# prueba rápida de tasa (requiere la laptop asociada al Wi-Fi):
sudo ping -i 0.006 -s 0 192.168.0.75 >/dev/null 2>&1 &
python3 /home/pi/capture_csi.py 10      # debería dar ~92-95 CSI/s por placa
sudo pkill -f 'ping -i'
```

### 8.2 Los ESP32 (firmware)
Se graban una sola vez con ESP-IDF (ver [`esp32/CONFIG.md`](esp32/CONFIG.md)):
```bash
idf.py -p <puerto> flash     # graba el firmware csi_recv (sniffer)
```
Tras grabarlos, arrancan solos al recibir alimentación. No hace falta tocar nada en cada captura
(salvo el reset por software si quedaron en ROM).

### 8.3 Capturar el dataset (PC, Windows)
```bash
cd pc
# todas las acciones guiadas (resetea ESP32, cuenta 3 s, captura, empareja y formatea):
python capturar_acciones.py

# una sola acción:
python capturar_acciones.py A03

# más duración por acción (más frames):
python capturar_acciones.py --dur 40
```

### 8.4 Entrenar y evaluar
```bash
cd pc
python entrenar_v2.py 60      # split 70/15/15 cronológico por acción
python test.py                # métricas ICP sobre el TEST reservado
python vis_matta.py A03 10    # visualización GT vs predicho (colores de Määttä)
python video_pred.py          # GIF animado de la generación de puntos
```

> En la universidad (PC con mejores componentes) el entrenamiento se lanza con un solo paso:
> ver [`ENTRENAMIENTO.md`](ENTRENAMIENTO.md).

---

## 9. Evaluación

Split **70/15/15 cronológico por acción** (sin fuga temporal: frames vecinos casi idénticos nunca se
reparten entre train y test). Métricas sobre el **test reservado** (`pc/test.py`):
- **ICP fitness** — fracción de puntos con correspondencia dentro de un umbral.
- **ICP RMSE** — error de esas correspondencias (metros).
- **Chamfer** — distancia bidireccional media (referencia de reconstrucción/cobertura).

Las nubes GT (Kinect) y predicha (IA) se visualizan con los **colores de Määttä**
(colormap `viridis` según distancia al sensor).

---

## 10. Estructura del repositorio

```
pc/      scripts de la PC (captura, emparejado, formato, entrenamiento, test, visualización)
pi/      scripts de la Raspberry Pi (lectura de los ESP32 y generación de tráfico)
kinect/  captura de nubes con Azure Kinect + visores 3D
esp32/   configuración del firmware de los sniffers (esp32/CONFIG.md)
docs/    documentación técnica (docs/RED_Y_TRAFICO.md: red, tráfico, PPDUs, ICMP, límites)
README.md          este archivo
ENTRENAMIENTO.md   cómo entrenar el modelo (un paso) en la universidad
requirements.txt   librerías
entrenar_universidad.bat / .sh   entrenamiento en un paso (Windows / Linux)
```

---

## 11. Referencias
- T. Määttä, S. Sharifipour, M. Bordallo López, C. Álvarez Casado,
  *"Spatio-Temporal 3D Point Clouds from WiFi-CSI Data via Transformer Networks"*,
  IEEE Int. Symp. on Joint Communications & Sensing (JC&S), 2025.
  Código: https://github.com/Arritmic/csi2pointcloud
- Dataset **MM-Fi**: mediciones multimodales de CSI y actividades humanas.
- Proyecto **esp-csi** (Espressif): captura de CSI con ESP32.
```
> El modelo (arquitectura `CSI2PointCloudModel` y la pérdida Chamfer) proviene del repositorio oficial
> de Määttä (`csi2pointcloud`), **incluido en este repo bajo licencia MIT** (ver
> `csi2pointcloud/LICENSE`, © 2024 Constantino Álvarez). Este repositorio aporta el pipeline de
> captura, formateo, entrenamiento y evaluación con **hardware y datos propios**.
```
