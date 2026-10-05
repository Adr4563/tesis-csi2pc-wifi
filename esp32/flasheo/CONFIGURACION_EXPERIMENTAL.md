# Configuración Experimental — Captura CSI para reconstrucción 3D

Tesis: Reconstrucción de nubes de puntos 3D del cuerpo humano a partir de CSI Wi-Fi.

## Sala

Dimensiones: **2.80 m × 2.40 m** (280 × 240 cm), medidas con wincha.

## Hardware

| Componente | Modelo |
|---|---|
| Transmisor (TX) | TP-Link **Archer AX53** |
| Receptores (RX) | 3× **ESP32-S3** |
| Banda / ancho | 2.4 GHz / **40 MHz (802.11n HT40)** |
| Subportadoras | **114** (108 útiles) |
| Ground truth | Cámara **Intel RealSense** (NO LiDAR; el LiDAR es de MM-Fi) |
| Firmware | **esp-csi** (ejemplo csi_recv_router) de Espressif, ESP-IDF v5.3.2 |

## Distribución espacial (coordenadas en cm; origen abajo-izquierda)

El sujeto mira hacia la RealSense (dirección +y). El TX y RX1 están detrás del
sujeto; RX2 y RX3 a los lados; la RealSense al frente con vista limpia.

| Punto | Coord (x, y) cm | Coord (m) | Dist. al sujeto |
|---|---|---|---|
| Sujeto (mira +y) | (140, 90) | (1.40, 0.90) | — |
| RealSense (frente) | (140, 235) | (1.40, 2.35) | ~145 cm |
| Router TX (atrás) | (140, 20) | (1.40, 0.20) | ~70 cm |
| RX1 (atrás) | (140, 30) | (1.40, 0.30) | 60 cm |
| RX2 (izquierda) | (45, 100) | (0.45, 1.00) | ~96 cm |
| RX3 (derecha) | (235, 100) | (2.35, 1.00) | ~96 cm |
| Laptop (captura) | (140, 5) | (1.40, 0.05) | — |

Altura de los 3 RX: ~120 cm (torso). RealSense en trípode, algo más alta que el
router para que este no bloquee la vista del cuerpo.

```
  (0,240)                                        (280,240)
    +----------------------------------------------+
    |           [RealSense] (140,235)  ~1.45 m     |  ground truth
    |                                              |
    |  (RX2)                              (RX3)     |
    |  (45,100)     [Sujeto mira ^]   (235,100)     |
    |              (140,90)                         |
    |                 (RX1) (140,30)                |
    |              [Router TX] (140,20)  ~70 cm    |
    |              [Laptop]                         |
    +----------------------------------------------+
  (0,0)                                          (280,0)
```

## Justificación

- RealSense con vista limpia del sujeto (RX a los lados/atrás, no adelante).
- Sujeto da la cara al ground truth.
- TX a ~70 cm del sujeto, cercano a la distancia de MM-Fi (0.75 m).
- Triángulo de RX alrededor del sujeto = variable independiente (distribución espacial).

## Diferencias respecto a MM-Fi / Määttä (declarar en la tesis)

| | MM-Fi (Määttä) | Este trabajo |
|---|---|---|
| Sala | 8.5 × 7.8 m | 2.8 × 2.4 m |
| RX → sujeto | 3.0 m | 0.6–1.0 m |
| TX → sujeto | 0.75 m | ~0.70 m |
| Receptores | 3 antenas en 1 plataforma (coherentes) | 3 ESP32-S3 separados (NO coherentes) |
| Ground truth | LiDAR | Intel RealSense |
| Enfoque | 1 vista lejana | RX distribuidos alrededor (múltiples ángulos) |

## Experimentos

- Exp 1 y Exp 2: ambos con topología triangular, variando la distancia/tamaño del
  triángulo (la distribución espacial de los RX es la variable independiente).
- Split de datos: por repeticiones completas (evitar data leakage con 1 sujeto).
