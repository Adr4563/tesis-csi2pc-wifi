# Captura de CSI Wi-Fi con ESP32-S3 — Configuración y Observaciones

Documentación del montaje para la tesis "Reconstrucción de nubes de puntos 3D del
cuerpo humano a partir de señales CSI de redes Wi-Fi" (Adrian Flores, U. de Lima).

Última actualización: 2026-09-27

---

## 1. Objetivo

Capturar **Channel State Information (CSI)** de Wi-Fi usando receptores ESP32-S3,
con el **router como transmisor (TX)**, para alimentar el modelo CSI2PC.

---

## 2. Hardware

| Elemento | Detalle |
|---|---|
| Transmisor (TX) | Router **TP-Link Archer AX53** (AX3000), 2.4 GHz, canal 6 |
| Receptores (RX) | 3× **ESP32-S3** (USB nativo, VID 303A) |
| Host de captura | Raspberry Pi 4 (Ubuntu 26.04) y/o PC (Windows 10) |
| Ground truth | Cámara Intel RealSense / Kinect |

### MACs de las placas ESP32-S3
| MAC | Rol asignado |
|---|---|
| `3c:dc:75:62:21:4c` | RX1 |
| `dc:da:0c:6c:aa:78` | RX2 (USB nativo) |
| `d4:05:92:79:8e:40` | RX3 (era el TX original) — placa flasheada con csi_recv_router |
| `d4:05:92:79:9f:18` | repuesto (tuvo problemas de cable) |

---

## 3. Topología de red

```
Movistar (192.168.1.1)  ──cable──►  TP-Link Archer AX53 (192.168.0.1)
                                          │  crea red 192.168.0.x
                                          ├─ PC        192.168.0.218 (cable)
                                          └─ Raspberry 192.168.0.179 (wlan0) / .178 (eth0)
```

- **Archer BSSID 2.4 GHz:** `3c:78:95:2b:86:2f` (canal 6)
- **Archer BSSID 5 GHz:** `3c:78:95:2b:86:2e`

---

## 4. Configuración del router (TP-Link Archer AX53)

Panel: `http://192.168.0.1`

| Ajuste | Valor | Motivo |
|---|---|---|
| Smart Connect | **OFF** | Separar 2.4 y 5 GHz para controlar la banda |
| 2.4 GHz — Canal | **6 (fijo)** | Los RX escuchan canal 6 |
| 2.4 GHz — Channel Width | **40 MHz** | Para HT40 / 114 subportadoras (o 20 MHz para 64) |
| 2.4 GHz — Mode | 802.11 b/g/n(/ax) | HT (n) para el CSI |
| 5 GHz | **Enabled** | Para el internet de casa, deja limpia la 2.4 GHz |

---

## 5. Configuración de la Raspberry Pi

Se conecta sola al router (config persistente en `/etc/netplan/50-cloud-init.yaml`):

```yaml
network:
  version: 2
  ethernets:
    eth0: { dhcp4: true, optional: true }
  wifis:
    wlan0:
      dhcp4: true
      optional: true
      access-points:
        "TP-Link-Archer":
          password: "Chato7781"
          bssid: "3c:78:95:2b:86:2f"   # fija a la radio 2.4 GHz (canal 6)
```

- Acceso SSH: `pi@192.168.0.179` (wlan0) o `pi@192.168.0.178` (eth0).
- Lectura del ESP32 en la Pi: `/dev/ttyACM0`. **Usar pyserial con `dtr=False` y
  `rts=False` ANTES de `open()`** (por defecto pyserial los pone en True y resetea/silencia
  el chip). El board hace 1 reset al abrir el puerto: `rst:0x15 (USB_UART_CHIP_RESET)`, normal.

---

## 6. Firmware — el punto clave

### Lo que NO funcionó
El **ESP32-CSI-Tool de Steven Hernandez** (modo passive) capturaba muy poco
(~0.1–1 CSI/s) del router, solo frames legacy de terceros. No sirve para este escenario.

### Lo que SÍ funciona ✅
Firmware **oficial de Espressif**: `esp-csi/examples/get-started/csi_recv_router`.
El ESP32 se conecta al router y se auto-pinguea (`CONFIG_SEND_FREQUENCY=100`),
capturando el CSI de las respuestas del router.

- Repo: https://github.com/espressif/esp-csi
- Copia local: `Carpeta_Trabajo\esp-csi\`
- ESP-IDF: **v5.3.2** en `C:\esp\esp-idf`

### Configuración del proyecto (sin menuconfig)
En `csi_recv_router/sdkconfig.defaults`:
```
CONFIG_EXAMPLE_WIFI_SSID="TP-Link-Archer"
CONFIG_EXAMPLE_WIFI_PASSWORD="Chato7781"
```

### FIX para 114 subportadoras HT40
En `main/app_main.c`, rama `#else` (la que usa el ESP32-S3), venían APAGADOS.
Cambiar a `true`:
```c
wifi_csi_config_t csi_config = {
    .lltf_en           = true,
    .htltf_en          = true,   // <-- era false (solo daba 64 subp / LLTF)
    .stbc_htltf2_en    = true,   // <-- era false
    .ltf_merge_en      = true,
    .channel_filter_en = true,
    .manu_scale        = true,
    .shift             = true,
};
```

---

## 7. Compilar, flashear y leer

Activar el entorno (PowerShell): `. C:\esp\esp-idf\export.ps1`

```bash
cd Carpeta_Trabajo\esp-csi\examples\get-started\csi_recv_router
idf.py set-target esp32s3
idf.py build
idf.py -p COM7 flash
```

Leer el CSI: puerto serie a **921600 baud**.

---

## 8. Resultados medidos

| Config | Subportadoras | Tasa | len (bytes) | F = ×3 RX |
|---|---|---|---|---|
| HT20 (htltf_en=false) | 64 | ~100/s | 128 | 192 |
| **HT40 (htltf_en=true)** | **114** (108 usables) | **~54/s** | 380 / 612 | **342** (= Määttä) |

- Fuente confirmada: MAC `3c:78:95:2b:86:2f` (**el Archer**), `sig_mode=1` (HT),
  `cwb=1` (40 MHz), `sec_chan=2` (BELOW), `channel=6`.
- `len=380` = LLTF + HT-LTF ; `len=612` = LLTF + HT-LTF + STBC-HT-LTF (por `stbc=1`).
- **Trade-off:** con 114 la tasa baja de ~100 a ~54/s porque cada paquete es ~5× más grande
  a 921600 baud. Para recuperar 100/s: subir el baud, recortar la salida al HT-LTF, o
  mejorar la lectura.

---

## 9. Formato de la línea CSI (esp-csi)

```
CSI_DATA,id,mac,rssi,rate,sig_mode,mcs,bandwidth(cwb),smoothing,not_sounding,
aggregation,stbc,fec_coding,sgi,noise_floor,ampdu_cnt,channel,secondary_channel,
local_timestamp,ant,sig_len,rx_format,len,first_word,data
```
- `data` = array de int8 (cada subportadora = 2 valores: imaginario y real).
- Amplitud = √(imag² + real²) ; Fase = atan2(imag, real).

---

## 10. Hallazgos / correcciones importantes

1. El ESP32-S3 **SÍ captura 802.11n (HT) y HT40** — no es exclusivo del Intel 5300.
2. El `len=128` NO era límite del hardware, era `htltf_en=false` en la config.
3. El "router como TX" funciona; no hace falta un ESP32 transmisor dedicado.
4. Co-locar el RX pegado al TX satura el receptor: TX y RX deben estar separados.
5. HT40 en 2.4 GHz puede ser más ruidoso (verificar calidad del CSI).

---

## 11. Pendientes

- [ ] Flashear los otros 2 RX con este mismo firmware.
- [ ] Recuperar ~100/s con 114 subportadoras (subir baud / recortar salida).
- [ ] Script de captura que lea los 3 RX y guarde CSV con marca de tiempo (alinear con Kinect).
- [ ] Montaje físico: TX de un lado, 3 RX en triángulo separados, sujeto al centro.
- [ ] Corregir el borrador: tensor de entrada `[3 × 114 × 2 × T]`, F = 342.
