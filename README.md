# 🥽 VR Streaming - PC to iPhone

Sistema completo de streaming VR desde PC a iPhone usando conexión WiFi o USB. Convierte tu iPhone en un visor VR para tu pantalla de PC con seguimiento de cabeza mediante los sensores del dispositivo.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-green.svg)
![Swift](https://img.shields.io/badge/swift-5.0%2B-orange.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20iOS-lightgrey.svg)

## 📋 Tabla de Contenidos

- [Características](#-características)
- [Requisitos del Sistema](#-requisitos-del-sistema)
- [Instalación](#-instalación)
  - [Aplicación de PC (Windows)](#aplicación-de-pc-windows)
  - [Aplicación iOS](#aplicación-ios)
- [Uso](#-uso)
- [Configuración](#-configuración)
- [Arquitectura](#-arquitectura)
- [Solución de Problemas](#-solución-de-problemas)
- [Desarrollo](#-desarrollo)
- [Licencia](#-licencia)

## ✨ Características

### Aplicación de PC
- 📺 Captura de pantalla de alto rendimiento (60+ FPS)
- 👁️ Conversión estereoscópica lado a lado
- 🔄 Distorsión barrel para lentes VR
- 🔌 Conexión WiFi y USB
- 🎮 Control de mouse con sensores del iPhone
- ⚙️ Interfaz gráfica moderna para configuración
- 📊 Métricas en tiempo real (FPS, latencia, ancho de banda)

### Aplicación iOS
- 📱 Recepción de stream de video en tiempo real
- 🎯 Seguimiento de cabeza con giroscopio/acelerómetro
- 🖼️ Renderizado Metal de alto rendimiento
- 🔲 Vista estereoscópica con distorsión barrel
- ⚡ Baja latencia optimizada para VR
- 🔄 Recentrado de vista con un toque

## 💻 Requisitos del Sistema

### PC (Windows)
- Windows 10/11 (64-bit)
- Python 3.10 o superior
- Tarjeta gráfica compatible con DirectX 11
- Conexión WiFi o puerto USB

### iPhone
- iPhone 6s o posterior (recomendado iPhone 12+)
- iOS 15.0 o superior
- Giroscopio y acelerómetro (todos los iPhones compatibles)

### Hardware Adicional
- Visor VR para smartphone (Google Cardboard, etc.)
- Cable Lightning a USB (para conexión USB)
- Red WiFi local (para conexión WiFi)

## 🚀 Instalación

### Aplicación de PC (Windows)

#### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/vr-streaming.git
cd vr-streaming
```

#### 2. Crear entorno virtual

```bash
cd pc-app
python -m venv venv
venv\Scripts\activate
```

#### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

> **Nota**: Algunas dependencias como `dxcam` son específicas de Windows. En otros sistemas, la captura de pantalla usará `mss` automáticamente.

#### 4. Ejecutar la aplicación

```bash
python main.py
```

Para modo sin GUI (headless):
```bash
python main.py --headless --port 8889
```

### Aplicación iOS

#### Opción 1: Descargar IPA pre-compilado

1. Ve a la sección [Releases](https://github.com/tu-usuario/vr-streaming/releases) del repositorio
2. Descarga el archivo `VRStreaming-unsigned.ipa` más reciente
3. Continúa con la instalación usando Sideloadly (ver abajo)

#### Opción 2: Compilar desde el código fuente

1. Abre `ios-app/VRStreaming.xcodeproj` en Xcode
2. Selecciona tu Team de desarrollo en Signing & Capabilities
3. Conecta tu iPhone
4. Selecciona tu dispositivo como destino
5. Haz clic en Run (⌘R)

#### Instalación con Sideloadly

[Sideloadly](https://sideloadly.io/) permite instalar aplicaciones iOS sin cuenta de desarrollador de Apple.

1. **Descargar e instalar Sideloadly**
   - Ve a [sideloadly.io](https://sideloadly.io/)
   - Descarga la versión para tu sistema operativo
   - Instala la aplicación

2. **Preparar tu iPhone**
   - Conecta tu iPhone al PC vía USB
   - Confía en el dispositivo si se solicita
   - Asegúrate de tener iTunes instalado

3. **Instalar el IPA**
   - Abre Sideloadly
   - Arrastra el archivo `.ipa` a Sideloadly
   - Ingresa tu Apple ID (puede ser una cuenta gratuita)
   - Ingresa tu contraseña o genera una App-Specific Password
   - Haz clic en "Start"

4. **Confiar en el desarrollador**
   - En tu iPhone, ve a: Ajustes > General > Gestión de dispositivos
   - Toca tu Apple ID
   - Toca "Confiar"

> **Nota**: Con una cuenta gratuita de Apple, necesitarás reinstalar la app cada 7 días.

## 📖 Uso

### Inicio Rápido

1. **Inicia la aplicación de PC**
   ```bash
   cd pc-app
   python main.py
   ```

2. **Anota la dirección IP de tu PC**
   - Aparece en la ventana de la aplicación
   - O usa `ipconfig` en el terminal

3. **Inicia la aplicación iOS**
   - Abre VR Streaming en tu iPhone
   - Ingresa la IP del PC y el puerto (por defecto: 8889)
   - Toca "Connect"

4. **Coloca tu iPhone en el visor VR**
   - Una vez conectado, verás la pantalla de tu PC en estéreo
   - Mueve tu cabeza para controlar el mouse

### Controles de la Aplicación PC

| Botón | Función |
|-------|---------|
| ▶ Start Streaming | Inicia la captura y el servidor |
| ⏹ Stop Streaming | Detiene todo |
| 🎯 Recenter | Recentra el seguimiento |
| 💾 Save Settings | Guarda la configuración |

### Configuración de Video

- **Calidad**: 1-100 (mayor = mejor calidad, más latencia)
- **FPS**: 30-120 (ajusta según tu hardware)
- **Distorsión Barrel**: Activa para visores VR con lentes

### Configuración de Sensores

- **Sensibilidad**: Velocidad de movimiento del mouse
- **Suavizado**: Reduce el temblor (0 = sin suavizado)
- **Zona Muerta**: Ignora movimientos pequeños

## ⚙️ Configuración

### Archivo config.json

```json
{
    "video": {
        "capture_fps": 60,
        "output_resolution": {
            "width": 1920,
            "height": 1080
        },
        "quality": 85,
        "encoder": "jpeg",
        "use_dxcam": true,
        "monitor_index": 0
    },
    "stereoscopic": {
        "enabled": true,
        "eye_separation": 63.0,
        "fov": 100,
        "barrel_distortion": {
            "enabled": true,
            "k1": 0.22,
            "k2": 0.24
        }
    },
    "connection": {
        "mode": "wifi",
        "usb_port": 8888,
        "wifi_host": "0.0.0.0",
        "wifi_port": 8889,
        "buffer_size": 65536
    },
    "sensor_processing": {
        "sensitivity": {
            "yaw": 2.0,
            "pitch": 1.5,
            "roll": 1.0
        },
        "smoothing": 0.3,
        "deadzone": 0.02
    }
}
```

### Parámetros Importantes

| Parámetro | Descripción | Valores |
|-----------|-------------|---------|
| `capture_fps` | FPS de captura objetivo | 30-120 |
| `quality` | Calidad JPEG | 1-100 |
| `use_dxcam` | Usar DirectX para captura | true/false |
| `barrel_distortion.k1` | Distorsión primaria | 0.0-0.5 |
| `barrel_distortion.k2` | Distorsión secundaria | 0.0-0.5 |
| `sensitivity.yaw` | Sensibilidad horizontal | 0.5-5.0 |
| `sensitivity.pitch` | Sensibilidad vertical | 0.5-5.0 |

## 🏗️ Arquitectura

### Flujo de Datos

```
┌─────────────────────────────────────────────────────────────────┐
│                         PC (Windows)                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Screen    │──│   Stereo    │──│   Video     │──┐           │
│  │   Capture   │  │  Converter  │  │   Encoder   │  │           │
│  │  (dxcam)    │  │             │  │   (JPEG)    │  │           │
│  └─────────────┘  └─────────────┘  └─────────────┘  │           │
│                                                      │           │
│  ┌─────────────┐  ┌─────────────┐                    ▼           │
│  │   Mouse     │──│   Sensor    │◄──────────── USB/WiFi         │
│  │   Control   │  │  Processor  │               Server          │
│  └─────────────┘  └─────────────┘                    │           │
└──────────────────────────────────────────────────────┼───────────┘
                                                       │
                          WiFi / USB                   │
                                                       │
┌──────────────────────────────────────────────────────┼───────────┐
│                       iPhone                         │           │
│                                                      ▼           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Sensor    │──│  Streaming  │──│      Metal Renderer     │  │
│  │   Manager   │  │   Manager   │  │  (Stereo + Distortion)  │  │
│  │ (CoreMotion)│  │  (Network)  │  └─────────────────────────┘  │
│  └─────────────┘  └─────────────┘                                │
└──────────────────────────────────────────────────────────────────┘
```

### Protocolo de Comunicación

**PC → iPhone (Video)**
```
┌────────┬────────────┬────────────┬──────────────────┐
│ Magic  │ PacketType │ DataLength │     JPEG Data    │
│ (4B)   │   (4B)     │    (4B)    │    (Variable)    │
│ VRVI   │     0      │     N      │   N bytes        │
└────────┴────────────┴────────────┴──────────────────┘
```

**iPhone → PC (Sensores)**
```json
{
  "timestamp": 1234567890.123,
  "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
  "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
  "gyroscope": {"x": 0.0, "y": 0.0, "z": 0.0}
}
```

## 🔧 Solución de Problemas

### No puedo conectar al servidor

1. **Verifica que ambos dispositivos estén en la misma red WiFi**
2. **Desactiva temporalmente el firewall** o añade una excepción para Python
3. **Verifica la IP correcta**:
   ```bash
   ipconfig | findstr IPv4
   ```
4. **Prueba con el puerto por defecto (8889)**

### La imagen se ve con lag

1. **Reduce la calidad** en la configuración (60-75)
2. **Reduce el FPS objetivo** a 30
3. **Acerca el iPhone al router WiFi**
4. **Usa conexión USB** para mejor rendimiento

### Los sensores no funcionan

1. **Verifica los permisos** en iOS: Ajustes > Privacidad > Movimiento y fitness
2. **Recentra la vista** con el botón en la app iOS
3. **Reinicia la app iOS**

### El mouse no se mueve

1. **Verifica que los sensores estén enviando datos** (ver métricas)
2. **Aumenta la sensibilidad** en la configuración
3. **Reduce la zona muerta**

### Error "dxcam not available"

Esto es normal si no estás en Windows. La aplicación usará `mss` automáticamente como alternativa.

### Error de certificado en iOS

Al usar Sideloadly con cuenta gratuita:
1. El certificado expira cada 7 días
2. Reinstala la app con Sideloadly
3. Vuelve a confiar en el desarrollador

## 👨‍💻 Desarrollo

### Estructura del Proyecto

```
vr-streaming/
├── pc-app/
│   ├── main.py              # Entrada principal
│   ├── screen_capture.py    # Captura de pantalla
│   ├── video_encoder.py     # Codificación JPEG/H264
│   ├── usb_server.py        # Servidor TCP
│   ├── sensor_processor.py  # Procesamiento de sensores
│   ├── gui.py               # Interfaz gráfica
│   ├── config.json          # Configuración
│   └── requirements.txt     # Dependencias Python
├── ios-app/
│   ├── VRStreaming/
│   │   ├── VRStreamingApp.swift
│   │   ├── ContentView.swift
│   │   ├── VRDisplayView.swift
│   │   ├── StreamingManager.swift
│   │   ├── SensorManager.swift
│   │   ├── MetalRenderer.swift
│   │   └── Info.plist
│   └── VRStreaming.xcodeproj/
├── .github/
│   └── workflows/
│       └── build-ios.yml    # CI/CD para iOS
└── README.md
```

### Ejecutar Tests

```bash
cd pc-app
python -m pytest tests/
```

### Contribuir

1. Fork el repositorio
2. Crea una rama: `git checkout -b feature/nueva-caracteristica`
3. Commit tus cambios: `git commit -m 'Añade nueva característica'`
4. Push a la rama: `git push origin feature/nueva-caracteristica`
5. Abre un Pull Request

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Ver el archivo [LICENSE](LICENSE) para más detalles.

## 🙏 Agradecimientos

- [dxcam](https://github.com/ra1nty/DXcam) - Captura de pantalla de alto rendimiento
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) - GUI moderna para Python
- [pymobiledevice3](https://github.com/doronz88/pymobiledevice3) - Comunicación con dispositivos iOS

---

**¿Preguntas o problemas?** Abre un [Issue](https://github.com/tu-usuario/vr-streaming/issues) en GitHub.
