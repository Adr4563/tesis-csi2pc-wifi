> **NOTA (2026-10-06):** bitácora histórica. El firmware que se usa hoy es
> `esp32/csi_recv/` (csi_recv_router, 114 subportadoras HT40, router como TX).
> Los binarios `passive.bin` / `active-sta.bin` que se mencionan abajo quedaron
> **obsoletos** y se quitaron del repo. Ver [`../COMO_FLASHEAR.md`](../COMO_FLASHEAR.md).

# Estado del flasheo de placas ESP32-S3 — 2026-09-26

## Asignación de roles (ACTUALIZADA)

| Rol | MAC | Firmware | CSI verificado | Baud lectura (Windows) |
|---|---|---|---|---|
| RX1 | `3c:dc:75:62:21:4c` | passive ✅ | ✅ canal 6, 64 subp. | 115200 |
| RX2 | `dc:da:0c:6c:aa:78` | passive ✅ | ✅ canal 6, 64 subp. | 230400 (USB nativo) |
| RX3 | `d4:05:92:79:8e:40` | passive ✅ | ✅ canal 6, 64 subp. | 115200 |
| TX  | *por definir* | PENDIENTE (recompilar) | — | — |
| ¿?  | `d4:05:92:79:9f:18` | no conectó (cable/placa) | — | — |

## Cambios importantes respecto a la tabla original del repo (CONFIG.md)

- La placa `d4:05:92:79:8e:40` **antes era el TX**, ahora es **RX3** (passive).
- Por lo tanto, el **MAC del TX cambia**. Cuando se defina el TX, hay que:
  - Actualizar el filtro de MAC en `dataset_builder/build_dataset.py` con el NUEVO MAC del TX.
  - Actualizar la tabla de CONFIG.md.
- La placa `d4:05:92:79:9f:18` no logró conectar por USB (esptool: "No serial data received", auto-reset no funcionó). Revisar cable / puerto USB de la placa / probar modo descarga manual (BOOT+RESET). Candidata a ser el TX.

## Hallazgos técnicos confirmados

- **Subportadoras: 64** (no 128). El firmware está capado por `CONFIG_SHOULD_COLLECT_ONLY_LLTF=y` y escucha en 20 MHz (`WIFI_SECOND_CHAN_NONE`). Feature: F = 3 RX × 64 = 192.
- **Baud correcto de captura: 115200** para placas con puente UART; las de USB nativo el baud es indiferente en Linux (`/dev/ttyACM*`).
- Para 40 MHz / 128 subportadoras habría que RECOMPILAR el passive (quitar ONLY_LLTF + `WIFI_SECOND_CHAN_ABOVE`) — decisión pendiente; no es la variable de estudio de la tesis.

## Red / Archer AX54

- Archer en su propia red: **192.168.0.x**, panel en **http://192.168.0.1** (alcanzable desde la Raspberry por eth0 = 192.168.0.178).
- Raspberry Pi: Ubuntu 26.04, Wi-Fi wlan0 = 192.168.1.39 (red Movistar), eth0 al Archer.
- Router de casa (Movistar) = 192.168.1.1.
- Config pendiente en Archer: fijar canal 2.4 GHz = 6; ancho 20 MHz; anotar SSID/clave 2.4 GHz para recompilar el TX.

## Firmware y herramientas

- esptool v5.4.0 instalado en la PC (pip).
- Binarios passive/active_sta copiados en: `Carpeta_Trabajo\esp32_flash\firmware\`
- Comando de flasheo usado:
  `python -m esptool --chip esp32s3 --port COMxx --baud 921600 --before default-reset --after hard-reset write-flash --flash-mode dio --flash-size detect --flash-freq 80m 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 passive.bin`

## DIAGNÓSTICO de captura (2026-09-26, tarde)

Problema: con 1 RX en el PC (COM7) la captura es de ~0.2–1 pkt/s, siempre de equipos AJENOS
(A0:8A:06:0E:0C:4F, 50:D4:F7 = FLORES2, etc.), NUNCA del TX que queremos.

Hallazgos verificados:
- Archer AX53 configurado OK: canal 6 (2437 MHz), Smart Connect OFF, 5 GHz separado,
  modo 2.4 GHz cambiado a "802.11 b/g/n" (se quitó ax). BSSID 2.4G = 3c:78:95:2b:86:2f.
- Pi wlan0 conectada al Archer 2.4G (fijada por BSSID), IP 192.168.0.179. eth0=192.168.0.178.
- Ping 100/s Pi->Archer (unicast, HT) confirmado corriendo -> NO capturado por el RX.
- Ping broadcast 100/s (legacy) confirmado enviando (~92 tx_packets/s) -> TAMPOCO capturado.
- Lo ÚNICO que captura el RX: frames con sig_mode=0, rate=11 (802.11b DSSS) de equipos random.

Conclusión: el ESP32 passive solo está capturando frames legacy 802.11b de terceros; NO ve el
tráfico HT/OFDM del Pi/Archer. Causa probable: (a) distancia física RX<->Pi no controlada, y/o
(b) el ESP32-CSI-Tool está pensado para TX=ESP32 (active_sta), cuyos frames el RX ESP32 sí captura.

Servicios en la Pi para tráfico: 'csi-ping' (unicast) y 'csi-bcast' (broadcast) via systemd-run.
Parar: sudo systemctl stop csi-ping csi-bcast

PENDIENTE decidir: (1) probar con RX pegado físicamente al TX; (2) volver al diseño del repo
(ESP32 active_sta como TX, requiere ESP-IDF + SSID/clave Archer); (3) forzar TX a 802.11b.

## CORRECCIÓN IMPORTANTE (2026-09-26, noche)

- ❌ ERROR previo: dije "el ESP32 solo capta legacy 802.11b". FALSO.
- ✅ CONFIRMADO: el ESP32-S3 SÍ captura 802.11n (sig_mode=1). Capturado E0:BA:AD sm=1 (HT).
- ✅ Método de lectura correcto en la Pi (USB nativo ttyACM0):
    pyserial con s.dtr=False, s.rts=False ANTES de open(), y abrir UNA sola vez.
    (pyserial por defecto pone dtr/rts=True -> resetea/silencia el chip. cat funciona a veces.)
- El board resetea 1 vez al abrir el puerto: rst:0x15 (USB_UART_CHIP_RESET). Normal.
- Tasa de captura muy baja (~0.15/s) en la posición actual, y NO capta el ping de la propia Pi.

## Causa del "no capta el ping de la Pi": SATURACIÓN por co-locación
El ESP32 (RX) y el Wi-Fi de la Pi (TX) están en el mismo aparato pegados. La señal del TX
llega al RX demasiado fuerte y satura el receptor -> no decodifica. Para CSI, TX y RX deben
estar SEPARADOS en el espacio (que es justo el diseño del triángulo). Co-locar TX y RX rompe todo.

## Conclusión / próximo paso
El ESP32 funciona y capta HT. Falta el montaje físico correcto: TX en un lado, los 3 RX en el
triángulo (separados del TX), sujeto en el centro. Con tráfico HT/legacy fluyendo entre TX y un
cliente, los RX captan el CSI de esa señal al atravesar el espacio/cuerpo.

## ✅✅ SOLUCIÓN ENCONTRADA (2026-09-27) — csi_recv_router de Espressif

Con el firmware OFICIAL de Espressif `esp-csi/examples/get-started/csi_recv_router`:
- **102 CSI/s** medidos (objetivo 100/s) ✅
- Fuente = 3c:78:95:2b:86:2f = **EL ARCHER** (router como TX) ✅
- sig_mode=1 (HT/802.11n), mcs=7, canal 6, RSSI -21, len=128 (64 subp, bw=0/20MHz) ✅

CONCLUSIÓN: el "router como TX" SÍ da 100 CSI/s. El problema era el tool VIEJO (Steven Hernandez),
no el ESP32 ni el router. csi_recv_router se conecta al router y se auto-pinguea a 100/s (CONFIG_SEND_FREQUENCY=100).

Setup ESP-IDF (PC):
- ESP-IDF v5.3.2 en C:\esp\esp-idf ; toolchain instalado.
- Proyecto: Carpeta_Trabajo\esp-csi\examples\get-started\csi_recv_router
- WiFi en sdkconfig.defaults: CONFIG_EXAMPLE_WIFI_SSID="TP-Link-Archer" / PASSWORD="Chato7781"
- Compilar/flashear: activar env (. C:\esp\esp-idf\export.ps1), luego:
    idf.py set-target esp32s3 ; idf.py build ; idf.py -p COM7 flash
- Leer CSI: puerto a 921600 baud. Formato: CSI_DATA,id,mac,rssi,rate,sig_mode,mcs,bandwidth,...,channel,secondary_channel,...,len,data

PENDIENTE: repetir para los 3 RX; opcional HT40 para 114 subportadoras (ahora 64 en 20MHz).

## ✅✅✅ 114 SUBPORTADORAS HT40 LOGRADAS (2026-09-27)

CAUSA del len=128: en csi_recv_router, la rama #else (ESP32-S3) usa la API vieja de CSI con
.htltf_en=false y .stbc_htltf2_en=false -> solo capturaba el LLTF (64 subportadoras).

FIX (app_main.c, rama #else / ESP32-S3):
   .htltf_en       = true   (era false)
   .stbc_htltf2_en = true   (era false)
Recompilar + reflashear.

RESULTADO: len salta de 128 a 380/612 bytes.
  - len=380 (190 valores) = LLTF + HT-LTF -> contiene las 114 subportadoras HT40 (108 usables).
  - len=612 (306) = LLTF + HT-LTF + STBC-HT-LTF (por stbc=1).
Campos: sig_mode=1, cwb=1, sec_chan=2 (BELOW). Router en 40 MHz (Channel Width=40MHz).

TRADE-OFF: la tasa baja de ~100/s a ~54/s porque cada paquete es ~5x mas grande (612 vs 128 bytes)
a 921600 baud. Subir baud o aceptar ~50/s.

Conclusión: el ESP32-S3 SÍ da 114 subportadoras HT40. NO era limitación de hardware, era config.

## ✅ LOS 3 RX FLASHEADOS con csi_recv_router (2026-09-27)
- RX1 3c:dc:75:62:21:4c -> csi_recv_router (HT40/114) -> 47/s ✅
- RX2 dc:da:0c:6c:aa:78 -> csi_recv_router (HT40/114) -> 45/s ✅
- RX3 d4:05:92:79:8e:40 -> csi_recv_router (HT40/114) -> ~54/s ✅
Todas capturan del Archer 3c:78:95:2b:86:2f, sig_mode=1, cwb=1, len=612 (114 subp HT40).
Firmware con .htltf_en=true y .stbc_htltf2_en=true. WiFi TP-Link-Archer/Chato7781.
PENDIENTE: script que lea los 3 a la vez + marca de tiempo; recuperar 100/s; montaje triangular.

## MODELO CSI2PC (Määttä) - hallazgos (2026-09-27)
Repo: github.com/Arritmic/csi2pointcloud. CONFIRMADO: es supervisado, NECESITA ground truth.
- Entrena con dataset MM-Fi (Yang et al. NeurIPS 2023): modalidades rgb/depth/LiDAR/mmwave/wifi-csi.
- Ground truth = nube de puntos LiDAR (modelo exacto sin confirmar; posible Ouster). Submuestrea a 1000 pts.
- Pérdida = Chamfer distance (pred vs gt_lidar). test_model.py compara gt vs pred.
- SÍ hay checkpoints preentrenados (Google Drive, link en README) + video demo.
- torch 2.13.0+cpu ya instalado en la PC.
PENDIENTE si se retoma: bajar checkpoint, correr inferencia (mostrar nube). El dataset MM-Fi
completo es enorme y con registro. Para la tesis: capturar CSI+Kinect pareado (ground truth propio).
