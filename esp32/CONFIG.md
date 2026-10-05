# Configuración de los ESP32-S3 (firmware de captura de CSI)

Los 3 sniffers usan el firmware del proyecto **esp-csi** de Espressif, ejemplo
`examples/get-started/csi_recv`, grabado en modo **sniffer (promiscuo)** sobre **ESP32-S3**.
Todos los valores de abajo son los **reales usados en este trabajo**.

> **El código del firmware modificado está en [`csi_recv/`](csi_recv/)** (junto a este archivo):
> `csi_recv/main/app_main.c` es la fuente con los cambios de este trabajo (canal 6, filtro por MAC
> del router, HT40/HT-LTF, `rx_seq`), y `csi_recv/sdkconfig(.defaults)` tiene la configuración de
> compilación (baud 4 Mbaud, target esp32s3). Son los archivos del proyecto `esp-csi` que se
> modificaron; el resto del repo `esp-csi` (componentes de Espressif) se clona aparte.

---

## 1. Parámetros de radio (deben coincidir con el router)

| Parámetro | Valor | Dónde se fija |
|---|---|---|
| **Chip** | ESP32-S3 | `CONFIG_IDF_TARGET="esp32s3"` |
| **Banda** | **2.4 GHz** | mismo canal que el Archer |
| **Canal** | **6** | `#define CONFIG_LESS_INTERFERENCE_CHANNEL 6` |
| **Ancho de banda** | **HT40 (40 MHz)** | `#define CONFIG_WIFI_BANDWIDTH WIFI_BW_HT40` |
| **Canal secundario** | **WIFI_SECOND_CHAN_BELOW** | para HT40 (40 MHz = 20 principal + 20 secundario) |
| **Subportadoras** | **114** | HT40 con HT-LTF (`CSI_FORCE_LLTF = 0`) |
| **PHY / rate** | HT40, MCS0 LGI | `WIFI_PHY_MODE_HT40`, `WIFI_PHY_RATE_MCS0_LGI` |
| **Control de ganancia** | activado | `CONFIG_GAIN_CONTROL 1` |

> El **router (TP-Link Archer AX53)** debe estar en **2.4 GHz, canal 6, ancho 40 MHz (HT40)**
> para que coincida con los sniffers. Si el router no está en HT40, no se obtienen las 114
> subportadoras esperadas.

---

## 2. Filtro por MAC del router

Solo se procesan las tramas cuyo **origen es la MAC del router** (el transmisor de interés):

```c
static const uint8_t CONFIG_ROUTER_MAC[] = {0x3c, 0x78, 0x95, 0x2b, 0x86, 0x2f};
```
```c
// en el callback de CSI, se descarta todo lo que no venga del router:
if (memcmp(info->mac, CONFIG_ROUTER_MAC, 6)) return;
```

Esto deja fuera el ruido de otros equipos y asegura que cada medición CSI corresponde a una
**trama transmitida por el router al aire**.

---

## 3. Salida por UART/USB

| Parámetro | Valor | Motivo |
|---|---|---|
| **Baudrate** | **4 000 000 (4 Mbaud)** | `CONFIG_ESP_CONSOLE_UART_BAUDRATE=4000000` |
| **Formato** | texto CSV por línea, cada una empieza con `CSI_DATA` | la Pi filtra por ese prefijo |
| **Campo extra** | `rx_seq` (número de secuencia 802.11) | añadido para sincronizar las 3 placas |

**Por qué 4 Mbaud:** cada línea de CSI en HT40 ocupa ~2500 bytes (114 subportadoras × I/Q en texto).
A ~100 muestras/s eso son ~250 KB/s ≈ **2 Mbit/s** por placa solo de CSI. A 2 Mbaud el serial se
satura (~90/s máx.); a **4 Mbaud** hay margen para ~100–180/s sin perder líneas.

**Formato del CSI crudo:** valores I/Q intercalados (par = Q, impar = I); amplitud = `|I+jQ|`,
fase = `angle(I+jQ)`. En HT40 las 114 subportadoras útiles se extraen concatenando los índices
`[66:123]` y `[127:184]` de los 306 valores crudos.

---

## 4. Grabar el firmware (una sola vez por placa)

Con ESP-IDF instalado. Hay dos formas:

**A) Usando el firmware ya modificado de este repo:**
```bash
git clone https://github.com/espressif/esp-csi     # componentes de Espressif
# copiar los archivos modificados de este repo sobre el ejemplo:
cp -r esp32/csi_recv/* esp-csi/examples/get-started/csi_recv/
cd esp-csi/examples/get-started/csi_recv
idf.py set-target esp32s3
idf.py -p <PUERTO> flash    # <PUERTO> = COMx (Windows) o /dev/ttyACMx (Linux)
```

**B) Desde el ejemplo original**, aplicando a mano los cambios de la §1–§3 en `main/app_main.c`
y el baud en `menuconfig`:
```bash
cd esp-csi/examples/get-started/csi_recv
idf.py set-target esp32s3
idf.py menuconfig          # verificar baud 4000000 y canal 6
idf.py -p <PUERTO> flash
```

Tras grabarse, cada ESP32 arranca solo al recibir alimentación y empieza a sniffear en el canal 6.

---

## 5. Notas de operación

- **Alimentación:** los 3 ESP32-S3 sniffeando a ~100/s consumen bastante. Con los puertos USB de la
  Raspberry suele haber **brownout** → la placa se reinicia al **bootloader ROM** (`ESP-ROM:esp32s3…`)
  o se cae del bus USB. Alimentar con **más voltaje / hub USB con fuente externa**.
- **Recuperar una placa en ROM:** pulso de reset por software (toggle de la línea DTR a 115200);
  lo hace `pc/capturar_acciones.py` antes de cada captura.
- **Sincronización fina entre placas:** se usa el campo `rx_seq` (misma secuencia 802.11 ⇒ misma
  trama ⇒ mismo instante, con precisión sub-ms).
