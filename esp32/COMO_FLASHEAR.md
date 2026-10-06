# Firmware de los ESP32-S3 — cuál es y cómo grabarlo

## El firmware que se usa

**`csi_recv/`** — y es el único. Las 3 placas tienen este mismo código grabado.
Es `csi_recv_router` de Espressif con dos modificaciones propias.

| | |
|---|---|
| **TX** (transmite) | el router **TP-Link Archer AX53**, canal 6, 40 MHz — *no* un ESP32 |
| **RX** (escuchan) | las **3 placas ESP32-S3**, todas con `csi_recv/` |
| Salida | líneas `CSI_DATA,...` por USB con 384 valores I/Q = 114 subportadoras HT40 |

### Las 2 modificaciones sobre el ejemplo de Espressif

1. **Filtro por el MAC del router** (`app_main.c:58`): solo guarda el CSI del Archer
   y descarta el tráfico de terceros.
   ```c
   static const uint8_t CONFIG_ROUTER_MAC[] = {0x3c,0x78,0x95,0x2b,0x86,0x2f};
   ```
2. **HT-LTF activado** (`app_main.c:253-255`): sin esto solo salían 64 subportadoras
   (LLTF, 20 MHz). Con esto salen las 114 de HT40.
   ```c
   .lltf_en = true, .htltf_en = true, .stbc_htltf2_en = true,
   ```

No usa SSID ni contraseña: funciona en **modo promiscuo**, escuchando el aire.
Para otra red basta cambiar el MAC de la línea 58.

---

## ¿Hace falta reflashear?

**No.** El firmware queda en la memoria flash de cada placa y sobrevive a apagarlas
y desconectarlas. Conectas por USB y ya están capturando.

Solo hay que reflashear si: cambias el código, usas una placa nueva, o alguien
grabó otra cosa encima.

---

## Cómo grabarlo (si hiciera falta)

Requiere **ESP-IDF v5.3.2**.

```bash
# 1. Activar el entorno de ESP-IDF (PowerShell)
. C:\esp\esp-idf\export.ps1

# 2. Compilar
cd esp32/csi_recv
idf.py set-target esp32s3
idf.py build

# 3. Grabar (cambia COM7 por el puerto de la placa)
idf.py -p COM7 flash
```

Para leer el CSI después: `pi/capture_csi.py` lee las 3 placas en paralelo a
**4000000 baud** (`/dev/ttyACM*`, USB nativo). El baud alto es lo que permite
sostener ~95 CSI/s por placa: cada paquete HT40 son 384 valores, y a 921600
la tasa cae a ~50/s.

---

## Dos cosas que cuestan horas si no se saben

**1. pyserial resetea la placa.** Hay que poner `dtr` y `rts` en `False` *antes*
de `open()`, y abrir el puerto una sola vez. Por defecto pyserial los pone en
`True`, lo que resetea/silencia el chip. Ya está resuelto en `pi/capture_csi.py`.

**2. TX y RX deben estar separados en el espacio.** Si el transmisor está pegado
al receptor, la señal lo satura y no decodifica nada. Por eso el montaje es
triangular: router a un lado, los 3 RX separados, sujeto en el centro.

---

## Firmwares descartados (no usar)

Dos intentos previos, documentados en `flasheo/ESTADO_FLASHEO.md`:

| Firmware | Rol que tenía | Por qué se descartó |
|---|---|---|
| `active_sta` | un ESP32 como TX | Innecesario: el router hace de TX |
| `passive` | ESP32 como RX (tool de Steven Hernandez) | Solo 64 subportadoras y ~0.15 CSI/s |

Sus binarios `.bin` se quitaron del repo para no confundirlos con el firmware
real. Están en el historial de git si se necesitaran.

---

## Documentación relacionada

- [`CONFIG.md`](CONFIG.md) — configuración del firmware y de las placas
- [`flasheo/README.md`](flasheo/README.md) — hardware, topología de red, ajustes del router
- [`flasheo/ESTADO_FLASHEO.md`](flasheo/ESTADO_FLASHEO.md) — bitácora: MACs, problemas y cómo se resolvieron
- [`flasheo/CONFIGURACION_EXPERIMENTAL.md`](flasheo/CONFIGURACION_EXPERIMENTAL.md) — montaje del experimento
