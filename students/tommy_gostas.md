# Tommy Gostas

---

## Identidad

| Campo | Valor |
|---|---|
| Nombre completo | Tommy Gostas |
| Handle GitHub | @tommygostas98-dev |
| Correo de contacto | luisloo@hotmail.com |
| Repo personal del proyecto | https://github.com/tommygostas98-dev/amper-vigia (por publicar) |
| Fecha de registro | 2026-06-06 |

---

## Proyecto

| Campo | Valor |
|---|---|
| Nombre del agente | AmperVigía |
| Variante elegida | (1) Diagnóstico — sobrecarga y cortocircuito eléctrico en acometidas y bancos de transformadores |
| Modelo LLM | Claude Code (la propia sesión como cerebro, sin API key externa) |
| Canal de salida principal | correo (smtplib, con modo simulación); WhatsApp / Telegram / dashboard pendientes |
| PDFs base del RAG | Base curada en `data/conocimiento/` (IEEE C57.91, IEC 60909, NEC art. 240/450, NEMA MG-1). PDFs reales: pendientes |

---

## Clases POO propias

1. `Transformador` — equipo monitoreado (acometida/banco); calcula la corriente nominal de placa y guarda el historial de lecturas.
2. `LecturaElectrica` — medición trifásica puntual (Ia/Ib/Ic, Va/Vb/Vc, temperatura del aceite, factor de potencia).
3. `Diagnostico` — veredicto estructurado: severidad, falla probable, evidencia, acción y norma citada.

---

## Herramientas (tools) del agente

1. `analizar.py` — factor de carga, desbalance de fases y nivel de tensión; clasifica normal/sobrecarga/desbalance/cortocircuito (OK/ALERTA/CRÍTICO).
2. `rag.py` — RAG TF-IDF local sobre normas (IEEE/IEC/NEC/NEMA), sin API key.
3. `notificar.py` — envía el diagnóstico por correo (smtplib + `.env`, con modo simulación).
4. `agente.py` — orquestador: analiza, consulta normas y notifica las condiciones críticas.

---

## Estado actual

> Actualiza esta sección cada vez que tengas un hito. Una línea por entrada, fechada.

- `2026-06-06` · Registrado en el repo.
- `2026-06-06` · Agente **AmperVigía** punta a punta: 3 clases POO, 3 tools + orquestador, RAG (TF-IDF) sobre normas y correo (smtplib, modo simulación). Corre con `python agente.py`; 9/9 tests OK. LLM = Claude Code. Repo personal por publicar.

---

## Mensajes para otros estudiantes / instructor

> Espacio libre. Si tu agente quiere "decir" algo al resto de la clase, aquí lo escribe.

- `2026-06-06` (Tommy / AmperVigía → todos): Mi agente usa **Claude Code como cerebro** (sin API key externa), según el modelo de la clase. Variante 1 enfocada en **sobrecarga y cortocircuito** en transformadores. Pendiente: que el instructor me habilite push (colaborador) y comparta el **TOKEN** del MCP para engancharme a la mensajería.
