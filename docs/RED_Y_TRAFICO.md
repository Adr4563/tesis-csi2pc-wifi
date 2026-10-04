# Red, tráfico y tasa de CSI — detalle técnico

Documento específico de **cómo se genera el tráfico Wi-Fi** y por qué se llega a ~100 CSI/s.
Es el punto más delicado del montaje; aquí está todo lo que se probó y midió.

---

## 1. Concepto base: 1 CSI = 1 PPDU, no 1 paquete

El ESP32 obtiene **una medición de CSI por cada trama física (PPDU) que el router transmite al aire**
y que el sniffer recibe. **No** obtiene una por cada paquete de datos de la aplicación.

```
   paquetes de la app (miles/s)
            │
            ▼
   Router  ──► agrega varios paquetes en UNA sola trama física (A-MPDU)
            │
            ▼
   PPDUs transmitidas al aire  (decenas/s)   ← ESTO es lo que limita el CSI
            │
            ▼
   CSI capturado por el ESP32  (1 por PPDU recibida)
```

Consecuencia: **mandar más paquetes no sube el CSI** si el router los empaqueta (agrega) en pocas
PPDUs. Lo que importa es **cuántas PPDUs separadas emite el router**.

---

## 2. Topología del tráfico (quién transmite al aire)

| Enlace | ¿El router transmite al aire? | ¿Sniffable? |
|---|---|---|
| PC → router (Ethernet) | No (es cable) | No |
| Router → PC (Ethernet) | No (es cable) | No |
| Raspberry → router (subida Wi-Fi) | No (transmite la Pi, no el router) | No |
| **Router → laptop (bajada Wi-Fi)** | **Sí** | **Sí** |
| **Router → Raspberry (bajada Wi-Fi)** | **Sí** | **Sí** |

El sniffer filtra por **MAC del router**, así que solo cuentan las **bajadas** (router → cliente
inalámbrico). Por eso el destino del tráfico debe ser un **cliente Wi-Fi** (la laptop), para forzar al
router a **transmitir al aire** una y otra vez.

**Por qué la laptop y no la PC:** la PC está por **Ethernet**; el router nunca le transmite por aire,
así que no genera CSI. La laptop está por **Wi-Fi**: cada paquete que se le envía obliga al router a
emitir una PPDU al aire. Además la laptop **no necesita responder** — basta con que esté **asociada**
al router (su firewall puede descartar el ICMP y el CSI igual se genera).

---

## 3. Comparativa medida (misma red, 3 ESP32-S3)

| Tipo de tráfico | Paquetes enviados | CSI/s por placa | Nota |
|---|---|---|---|
| **UDP flood** a la laptop | miles/s | **~65/s** | se agrega mucho (A-MPDU) → pocas PPDUs |
| **ICMP flood** (`ping -f`) a la laptop | ~miles/s | **~88/s** | ICMP se agrega menos → más PPDUs |
| **ICMP** chico + 2 procesos | — | **~92/s** | paquetes mínimos, más PPDUs |
| **ICMP** a ritmo fijo `ping -i 0.006 -s 0` | ~166/s | **~92–97/s** | **configuración final** (apunta a ~100 sin pasarse) |
| ICMP al **router** (no a la laptop) | — | **~0/s** | el router no reenvía "al aire hacia sí mismo" |
| UDP/ICMP a la **PC** (Ethernet) | — | **~0/s** | la PC no es cliente inalámbrico |

**Conclusión:** el patrón de tráfico importa tanto como el volumen. El **ICMP a ritmo fijo hacia la
laptop** es lo que da la tasa objetivo de forma estable.

### Configuración final (la que usa `pi/flood.py`)
```bash
sudo ping -i 0.006 -s 0 192.168.0.75
#        │         │    └─ IP de la laptop (cliente Wi-Fi asociado)
#        │         └────── -s 0 : payload mínimo (más PPDUs por segundo)
#        └──────────────── -i 0.006 : ~166 paquetes/s → ~92-97 CSI/s tras agregación
```

---

## 4. Cuellos de botella y límites

### 4.1 Agregación A-MPDU del router
Es el límite principal. El Archer AX53 **no expone** un botón para desactivar A-MPDU, así que se
trabaja alrededor de él eligiendo tráfico que se agregue poco (ICMP) en vez de UDP masivo.

### 4.2 Serial USB (UART de los ESP32)
- Cada línea de CSI en HT40 ≈ **2500 bytes** (114 subportadoras × I/Q en texto).
- A ~100 muestras/s ⇒ ~250 KB/s ≈ **2 Mbit/s por placa** solo de CSI.
- A **2 Mbaud** el serial se satura (~90/s máx.). Por eso el firmware usa **4 Mbaud**
  (`CONFIG_ESP_CONSOLE_UART_BAUDRATE=4000000`), con margen para ~100–180/s sin perder líneas.

### 4.3 Alimentación USB (brownout de los ESP32)
Con los 3 ESP32-S3 a ~100/s, el consumo supera lo que dan los puertos USB de la Pi:
- Síntomas en `dmesg`: `USB disconnect`, `device not accepting address, error -71`,
  `unable to enumerate USB device`.
- Al leer el puerto aparece `ESP-ROM:esp32s3...` → la placa se reinició al **bootloader ROM** y dejó
  de sniffear (da **0 CSI** aunque haya tráfico).
- **Solución:** más voltaje / **hub USB con alimentación externa**. Con alimentación estable las 3
  placas se mantienen en **~92–95/s** sin caerse.
- Recuperación puntual: **pulso de reset por software** (toggle DTR a 115200), automático en
  `pc/capturar_acciones.py`.

---

## 5. Sincronización de relojes y de tramas

- **PC ↔ Raspberry:** relojes distintos. Se mide el **offset** (`t_pi − t_pc`) con un ping-pong por
  SSH (≈ 254 ms en este montaje) y se guarda en `pc_pi_offset.txt`. El emparejado
  (`pc/emparejar.py`) lo usa para alinear las nubes (reloj PC) con el CSI (reloj Pi) dentro de una
  tolerancia (60 ms).
- **Entre las 3 placas:** se usa el campo **`rx_seq`** (número de secuencia 802.11). Misma `rx_seq`
  ⇒ misma trama ⇒ mismo instante físico (precisión sub-ms), independiente del reloj de cada placa.

---

## 6. Checklist antes de capturar

1. Router en **2.4 GHz, canal 6, HT40 (40 MHz)**.
2. **Laptop asociada** a la red del Archer (si se cambió de red → 0 CSI). No importa que el ping
   diga "100% perdido" (firewall): mientras esté conectada, el CSI se genera.
3. ESP32 **alimentados con fuente estable** (hub con alimentación) y los 3 visibles como
   `/dev/ttyACM0/1/2`.
4. Prueba de tasa: debe dar **~92–97 CSI/s por placa**. Si da 0 → revisar laptop o si las placas
   quedaron en ROM (resetear).
