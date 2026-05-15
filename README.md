# Discord Video Compressor

Herramienta local para comprimir y convertir videos antes de enviarlos por Discord. Corre un servidor web en tu máquina y se maneja desde el navegador.

## Características

- **Modo Comprimir** — calcula el bitrate exacto para que el video entre en el límite de Discord (10 MB free, 50 MB Nitro, o lo que configures)
- **Modo Convertir** — convierte videos legacy (HandyCam, VHS capturado, DVD) a MP4 con calidad constante (CRF)
- **Encoders de hardware** — NVENC (Nvidia), AMF (AMD), Quick Sync (Intel) además de libx264/libx265 por CPU
- **Cola de trabajos** — procesa múltiples archivos en secuencia con progreso en tiempo real vía SSE
- **Explorador de archivos** integrado en el navegador, con soporte de unidades en Windows
- **Detección automática** de video entrelazado (480i, 1080i) con deinterlace yadif/bwdif
- **Corrección de SAR** para videos con píxeles no cuadrados

## Requisitos

- Python 3.10+
- [ffmpeg y ffprobe](https://ffmpeg.org/download.html) en el PATH

## Instalación

```bash
git clone https://github.com/tu-usuario/discord-compressor
cd discord-compressor
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

pip install flask
```

## Uso

```bash
python compressor.py
```

Abre `http://localhost:5000` en el navegador.

1. Navega al archivo desde el explorador lateral
2. Selecciona uno o más videos
3. Elige el modo (**Comprimir** o **Convertir**) y configura el encoder
4. Haz clic en **Agregar a cola** — el video se guarda como `nombre_discord.mp4` en la misma carpeta del original

## Perfiles de equipo

Los perfiles están definidos en [static/index.html](static/index.html) dentro del array `PC_PROFILES`. Cada uno especifica qué encoders de hardware tiene disponibles y cuántos threads usar. Edítalos para que coincidan con tu hardware.

| Perfil | Hardware |
|---|---|
| Desktop | i5-10400F + GT 1030 (NVENC) |
| Laptop | Ryzen 5 7520U + Radeon (AMF) |
| ThinkCentre | i5-8400T Ubuntu (QSV) |

## Encoders soportados

| Encoder | Tipo | Notas |
|---|---|---|
| `libx264` | CPU | Dos pasadas, máxima precisión de bitrate |
| `libx265` | CPU | ~30% mejor compresión que H.264 |
| `h264_nvenc` | GPU Nvidia | Ultra rápido, requiere driver reciente |
| `h264_amf` / `hevc_amf` | GPU AMD | Radeon RX 5000+ o APUs recientes |
| `h264_qsv` / `hevc_qsv` | iGPU Intel | Quick Sync, Gen 6+ |

## Estructura

```
discord-compressor/
├── compressor.py      # Servidor Flask + worker ffmpeg
└── static/
    └── index.html     # UI completa (JS vanilla, sin dependencias de build)
```
