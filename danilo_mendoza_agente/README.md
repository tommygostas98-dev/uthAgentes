# 🔧 Reporte y Análisis de falla en motor de combustión Wärtsilä W46

Herramienta para gestionar el mantenimiento de una planta: registro de equipos,
órdenes de trabajo, mantenimiento **preventivo** y **predictivo**, reportes de
costos, gestión de documentos y un **asistente con IA** (API de Claude) que
diagnostica fallas usando los datos reales de tus equipos.

## Características

- 📊 **Panel de control** con indicadores y alertas (preventivo + predictivo).
- 📋 **Equipos**: registro, edición completa, estado, horas de operación e
  historial por equipo.
- 🔧 **Órdenes de trabajo**: preventivo / correctivo / predictivo, con prioridad,
  responsable, cierre con solución y costo, y **reporte vinculado** a cada orden.
- ⏰ **Alertas de preventivo** por **días** y/o por **horas de operación**
  (lo que ocurra primero).
- 🔮 **Mantenimiento predictivo**: lecturas de sensores, límites de alerta/crítico,
  análisis de **tendencia** (regresión lineal) y **proyección** de cuándo se
  alcanzará el umbral. Incluye **importación masiva desde CSV/Excel**.
- 📈 **Reportes de costos**: por equipo, tipo y mes, con gráficos y exportación a
  **CSV, Excel y PDF**.
- 📄 **Documentos**: lista y descarga de todos los reportes generados.
- 📧 **Correo** (opcional): envío de reportes y alertas por Gmail.
- 🤖 **Asistente IA** que conoce el inventario, las órdenes y las horas de operación.

## Tecnología

- Python 3.12
- Streamlit (interfaz web)
- SQLite (base de datos local, archivo `data/mantenimiento.db`)
- pandas / numpy (datos y análisis predictivo)
- matplotlib + reportlab + python-docx + openpyxl (reportes PDF/Word/Excel)
- API de Claude (asistente IA) · smtplib (correo)

## Instalación

```powershell
# 1. (Opcional pero recomendado) crear un entorno virtual
python -m venv .venv
.venv\Scripts\Activate.ps1

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar (opcional) la clave de IA y el correo
copy .env.example .env
# luego edita .env (ver sección Configuración)
```

> La app funciona sin configuración (equipos, órdenes, predictivo, reportes).
> Solo el **asistente IA** y el **envío de correo** requieren credenciales.

## Uso

```powershell
streamlit run app.py
```

Se abrirá en el navegador (por defecto http://localhost:8501).

## Configuración (`.env`)

| Variable | Para qué | Obligatoria |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Asistente IA (console.anthropic.com) | Solo para IA |
| `ANTHROPIC_MODEL` | Modelo de Claude (por defecto `claude-sonnet-4-6`) | No |
| `GMAIL_USER` | Cuenta Gmail que envía los correos | Solo para correo |
| `GMAIL_APP_PASSWORD` | Contraseña de aplicación de Gmail (16 caracteres) | Solo para correo |
| `EMAIL_DESTINO` | Correo de destino por defecto | No |

> Gmail requiere **verificación en 2 pasos** + una **contraseña de aplicación**
> (https://myaccount.google.com/apppasswords). Alternativa sin contraseña:
> abrir Gmail web y adjuntar manualmente desde la sección 📄 Documentos.

## Secciones de la app

- **📊 Panel** — indicadores y alertas.
- **📋 Equipos** — alta/edición, horas de operación, historial.
- **🔧 Órdenes de trabajo** — alta, cierre, y vínculo con su reporte.
- **🔮 Predictivo** — análisis, registro de lecturas, importación CSV/Excel, límites.
- **📈 Reportes** — costos y exportación (CSV/Excel/PDF).
- **📄 Documentos** — descarga de reportes generados.
- **📧 Correo** — envío de reportes y alertas (requiere Gmail configurado).
- **🤖 Asistente IA** — diagnóstico y procedimientos.

## Importar lecturas de sensores (CSV/Excel)

En **🔮 Predictivo → 📥 Importar**: descarga la plantilla, sube tu archivo
(export de SCADA o histórico), mapea las columnas e importa. Columnas:
`parametro` y `valor` (obligatorias); `unidad`, `horas_operacion`, `fecha`
(opcionales — las horas son necesarias para proyectar tendencias).

## Estructura del proyecto

```
.
├── app.py                # Interfaz web (Streamlit)
├── requirements.txt
├── .env.example          # Plantilla de configuración
├── data/                 # Base de datos SQLite (se crea sola)
└── src/
    ├── database.py       # Conexión, esquema y migraciones SQLite
    ├── models.py         # CRUD de equipos y órdenes + alertas
    ├── predictivo.py     # Lecturas, límites, tendencias e importación
    ├── reportes.py       # Costos y exportación CSV/Excel/PDF
    ├── notificaciones.py # Envío de correos (Gmail SMTP)
    └── agente_ia.py      # Integración con la API de Claude
```

## Próximos pasos (ideas)

- Subida de fotos y manuales por equipo.
- Detección de anomalías más avanzada (media móvil, desviaciones).
- Importación de equipos y órdenes desde Excel.
- Usuarios y roles (técnico / supervisor).
- Alertas automáticas por correo programadas.
- Mantenimiento predictivo con sensores en tiempo real (proyecto MotorVigia).
```
