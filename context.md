# Contexto del Proyecto BitacoraKasu

> Sistema de gestión de flota vehicular para empresa de transporte mexicana.
> **Stack:** Django 5.2.7 · Python 3.14 · PostgreSQL (prod) / SQLite (dev) · DigitalOcean Spaces
> **Idioma:** Español (es-mx) · **Zona horaria:** America/Mexico_City · **Moneda:** MXN

---

## Arquitectura General

```
BitacoraKasu/
├── config/                         # Núcleo del proyecto Django
│   ├── settings.py                 # Configuración global
│   ├── urls.py                     # URLs raíz
│   ├── views.py                    # IndexView (dashboard principal)
│   ├── context_processors.py       # Inyecta alertas en todos los templates
│   ├── storage_backends.py         # Selector local / DigitalOcean Spaces
│   ├── scheduler.py                # Configuración APScheduler
│   ├── management/commands/
│   │   ├── runscheduler.py         # Inicia scheduler de reportes (proceso bloqueante)
│   │   └── test_reportes.py        # Prueba manual de reportes
│   ├── reportes/
│   │   ├── combustible.py          # enviar_reporte_combustible()
│   │   └── almacen.py              # enviar_reporte_almacen()
│   └── services/
│       └── google_maps.py          # GoogleMapsService (Distance Matrix API)
├── modulos/                        # Apps de dominio de negocio
│   ├── operadores/
│   ├── unidades/
│   ├── bitacoras/
│   ├── combustible/
│   ├── taller/
│   ├── compras/
│   └── almacen/
├── templates/                      # 79 templates HTML (extends base.html)
├── static/                         # CSS, JS, imágenes
└── media/                          # Archivos de usuario (dev local)
```

### Patrón de cada módulo

Cada app en `modulos/` sigue la misma estructura estándar:

| Archivo | Contenido |
|---------|-----------|
| `models.py` | Modelos con `verbose_name` en español, índices, `save()` overrides |
| `views.py` | Class-based views con `LoginRequiredMixin` |
| `urls.py` | Patrones de URL del módulo |
| `forms.py` | `ModelForm` con validaciones |
| `admin.py` | Configuración del panel Django Admin |
| `signals.py` | Lógica reactiva automática *(solo combustible, taller, almacen)* |

---

## Módulos del Sistema

---

### 1. `operadores` — Gestión de Conductores

**Propósito:** Catálogo y control de operadores (choferes) de la flota.

**Modelo principal:** `Operador`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `nombre` | CharField(200) | Nombre completo |
| `tipo` | choices | `LOCAL` / `FORANEO` / `ESPERANZA` |
| `unidad_asignada` | FK → Unidad | Vehículo asignado (nullable) |
| `licencia` | CharField | Número de licencia de conducir |
| `telefono` / `email` | | Datos de contacto |
| `activo` | BooleanField | Estado del operador |
| `fecha_ingreso` / `fecha_baja` | DateField | Control de vida laboral |
| `notas` | TextField | Observaciones |

**Métodos de negocio:**
- `horas_trabajadas_periodo(inicio, fin)` — suma horas de viajes completados en rango
- `viajes_completados()` — cuenta bitácoras con `fecha_llegada`
- `promedio_rendimiento()` — km/lt promedio real del operador

**Índices:** `(tipo, activo)`, `(nombre)`

**URLs:** 7 patrones (lista, crear, detalle, actualizar, eliminar, búsqueda)

**Vista de lista — Galería de tarjetas:**
- Diseño de galería tipo card grid igual que `unidades` (mismo CSS: `.fleet-card`, `.fleet-grid`, `.fleet-tooltip`)
- Tarjetas agrupadas por tipo: Locales (azul) / Foráneos (verde) / Esperanza (púrpura)
- Sin paginación (`paginate_by = None`); `get_context_data()` construye `grupos_operadores` dict
- Partial `_operador_card.html`: SVG inline de conductor con casco/volante, nombre truncado, 2 badges:
  1. Camión verde (unidad asignada) — activo si `operador.unidad_asignada`
  2. Ruta verde oscuro (viajes realizados) — activo si `operador.total_viajes > 0`
- Tooltip on hover: nombre, tipo, licencia, teléfono, email, unidad asignada, total viajes
- Patrón `next` preservado en links de editar/eliminar (desde vista de detalle)

---

### 2. `unidades` — Gestión de Vehículos

**Propósito:** Catálogo de vehículos con seguimiento de kilometraje, mantenimiento y eficiencia.

**Modelo principal:** `Unidad`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `numero_economico` | CharField(10, unique) | Identificador interno del vehículo |
| `placa` | CharField | Placa vehicular |
| `tipo` | choices | `LOCAL` / `FORANEA` / `ESPERANZA` |
| `marca` / `modelo` / `año` | | Datos técnicos (año: 1990-2030) |
| `capacidad_combustible` | DecimalField | Litros máximos del tanque |
| `rendimiento_esperado` | DecimalField | km/lt esperado (benchmark) |
| `kilometraje_actual` | IntegerField | Odómetro actualizado automáticamente |
| `activa` | BooleanField | Estado operativo |
| `ultimo_mantenimiento` / `proximo_mantenimiento` | DateField | Control de servicio |
| `control_combustible_total` | BooleanField (default=False) | Si `True`, fuerza el proceso completo de 6 pasos al cargar combustible, incluso en unidades LOCAL |

**Métodos de negocio:**
- `rendimiento_promedio_real()` — km/lt real basado en bitácoras completadas
- `eficiencia_combustible()` — % vs `rendimiento_esperado`
- `requiere_mantenimiento()` — `True` si `proximo_mantenimiento <= hoy`
- `viajes_completados()` — conteo de viajes

**Actualización automática de kilometraje:** Se actualiza desde tres fuentes:
1. `BitacoraViaje.save()` al completar un viaje
2. `CargaCombustible.save()` al completar una carga
3. `OrdenTrabajo.save()` al cerrar una OT con `kilometraje_salida`

**Admin especial:** Vista de actualización masiva de `rendimiento_esperado` por unidad.

**URLs:** 8 patrones (incluye `actualizar_rendimiento`)

---

### 3. `bitacoras` — Bitácoras de Viaje

**Propósito:** Registro detallado de cada viaje: ruta, tiempos, combustible, rendimiento y comparación con Google Maps.

**Modelo principal:** `BitacoraViaje`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `operador` | FK → Operador | Conductor del viaje |
| `unidad` | FK → Unidad | Vehículo utilizado |
| `modalidad` | choices | `SENCILLO` / `FULL` / `LOCAL` |
| `salida_a_ruta` | CharField(50) | Descripción de la ruta de salida |
| `contenedor` / `peso` / `sellos` | | Datos de carga del contenedor 1 |
| `contenedor_2` / `peso_2` / `sellos_2` | | Datos de carga del contenedor 2 (solo FULL) |
| `fecha_carga` / `fecha_salida` / `fecha_llegada` | DateTimeField | Tiempos del viaje |
| `diesel_cargado` | DecimalField | Litros cargados antes del viaje |
| `kilometraje_salida` / `kilometraje_llegada` | IntegerField | Odómetro |
| `cp_origen` (default: `40812`) / `cp_destino` | CharField | Códigos postales |
| `destino` | TextField | Descripción del destino |
| `distancia_calculada` / `duracion_estimada` | | Datos de Google Maps |
| `reparto` | BooleanField | Viaje con reparto de mercancía (no aplica a SENCILLO) |
| `observaciones` | TextField | Notas adicionales del viaje |
| `completado` | BooleanField | Auto `True` cuando llega `fecha_llegada` |

**Validaciones `clean()`:**
- `FULL` requiere `contenedor_2`
- `SENCILLO` no puede tener `contenedor_2`, `peso_2`, `sellos_2` ni `reparto`

**Propiedades calculadas** (no persistidas):
- `kilometros_recorridos` = `llegada - salida`
- `rendimiento_combustible` = km / litros
- `horas_viaje` — delta de fechas en horas
- `velocidad_promedio` — km/h
- `eficiencia_vs_esperado` — % vs `unidad.rendimiento_esperado`
- `diferencia_distancias` — km real vs Google Maps
- `alerta_bajo_rendimiento` — `True` si rendimiento < 2.5 km/lt

**Método `calcular_distancia_google()`:** Llama a `GoogleMapsService` y persiste `distancia_calculada` + `duracion_estimada`.

**`save()` override:**
1. Valida `fecha_llegada > fecha_salida`
2. Valida `kilometraje_llegada >= kilometraje_salida`
3. Auto-set `completado = True` si hay `fecha_llegada`
4. Actualiza `unidad.kilometraje_actual` si el viaje se completa

**Índices:** `(-fecha_salida)`, `(operador, fecha_salida)`, `(unidad, fecha_salida)`, `(completado)`

**URLs:** 10 patrones

| URL | Vista | Nombre |
|-----|-------|--------|
| `/bitacoras/` | `bitacora_dashboard` | `bitacoras:dashboard` |
| `/bitacoras/lista/` | `BitacoraListView` | `bitacoras:list` |
| `/bitacoras/crear/` | `BitacoraCreateView` | `bitacoras:create` |
| `/bitacoras/<pk>/` | `BitacoraDetailView` | `bitacoras:detail` |
| `/bitacoras/<pk>/editar/` | `BitacoraUpdateView` | `bitacoras:update` |
| `/bitacoras/<pk>/eliminar/` | `BitacoraDeleteView` | `bitacoras:delete` |
| `/bitacoras/<pk>/completar/` | `completar_viaje` | `bitacoras:completar` |
| `/bitacoras/<pk>/calcular-distancia/` | `calcular_distancia_ajax` (POST) | `bitacoras:calcular_distancia` |
| `/bitacoras/ajax/unidad-info/` | `unidad_info_ajax` (GET) | `bitacoras:unidad_info_ajax` |
| `/bitacoras/ajax/calcular-distancia/` | `calcular_distancia_preview_ajax` (GET) | `bitacoras:calcular_distancia_preview` |

**Dashboard (`bitacora_dashboard`):** Estadísticas globales — total, completados, en curso, por modalidad, diesel total, km totales, rendimiento promedio y alertas de bajo rendimiento.

**Filtros en `BitacoraListView`:** `search` (contenedor/destino/operador/unidad), `modalidad`, `completado` (true/false), `operador` (id), `unidad` (id), `fecha_desde`, `fecha_hasta`.

**Endpoints AJAX:**
- `unidad_info_ajax` — GET `?unidad_id=X` → placa, kilometraje, tipo, operador asignado
- `calcular_distancia_preview_ajax` — GET `?cp_origen=&cp_destino=` → distancia/duración sin guardar

**Patrón `next`:** `BitacoraUpdateView` y `BitacoraDeleteView` leen `request.GET.get('next')` para regresar al listado con filtros preservados.

**Templates:** 6 (`bitacora_dashboard.html`, `bitacora_list.html`, `bitacora_form.html`, `bitacora_detail.html`, `completar_viaje.html`, `bitacora_confirm_delete.html`)

---

### 4. `combustible` — Control de Carga de Combustible

**Propósito:** Registro fotográfico y de seguridad del proceso de carga de diésel, con detección automática de anomalías en candados.

**Modelos:**

#### `Despachador`
- Personal que opera las bombas de combustible
- Vinculado 1:1 a un `User` de Django (opcional)
- Campos: `nombre`, `telefono`, `activo`

#### `CargaCombustible` — Registro principal

**Wizard diferenciado por tipo de unidad:**

| Flujo | Pasos | Condición |
|-------|-------|-----------|
| **LOCAL simplificado** | Paso 1 → Paso 4 → Paso 6 (3 pasos) | `unidad.tipo == 'LOCAL'` y `control_combustible_total == False` |
| **Completo (FORÁNEO/ESPERANZA)** | Pasos 1 → 2 → 3 → 4 → 5 → 6 (6 pasos) | `unidad.tipo != 'LOCAL'` o `control_combustible_total == True` |

La detección ocurre en el POST del Paso 1. El `tipo_flujo` se persiste en la carga y en `request.session['carga_tipo_flujo']`. Los pasos 2, 3 y 5 están protegidos en `GET`: si se accede directamente durante flujo LOCAL, redirigen al paso 4.

| Campo | Tipo | Notas |
|-------|------|-------|
| `despachador` | FK → Despachador | — |
| `unidad` | FK → Unidad | — |
| `cantidad_litros` | DecimalField | Paso 4 |
| `kilometraje_actual` / `nivel_combustible_inicial` | | Paso 2 — solo flujo completo |
| `estado_candado_anterior` | choices | Paso 3 — solo flujo completo |
| `foto_numero_economico` | ImageField | Paso 1 |
| `foto_tablero` | ImageField (`null=True`) | Paso 2 — solo flujo completo |
| `foto_candado_anterior` | ImageField (`null=True`) | Paso 3 — solo flujo completo |
| `foto_candado_nuevo` | ImageField (`null=True`) | Paso 5 — solo flujo completo |
| `foto_ticket` | ImageField (`null=True`) | Paso 6 |
| `fecha_hora_inicio` / `fecha_hora_fin` / `tiempo_carga_minutos` | | Paso 4 |
| `tipo_flujo` | choices | `LOCAL` / `FORANEO` — trazabilidad del flujo usado |
| `estado` | choices | `INICIADO → EN_PROCESO → COMPLETADO / CANCELADO` |

**Estado del candado:** `NORMAL` / `ALTERADO` / `VIOLADO` / `SIN_CANDADO`

**Campos OCR (migración 0007):**
| Campo | Descripción |
|-------|-------------|
| `numero_candado_anterior` | Número leído por OCR de `foto_candado_anterior` |
| `ocr_candado_anterior_ok` | BooleanField — indica si el OCR ya se procesó |

**`save()` override:**
- Calcula `tiempo_carga_minutos` automáticamente
- Actualiza `unidad.kilometraje_actual` al completarse (solo si `kilometraje_actual > 0`)

**Signal en `combustible/signals.py` — refactorizado en funciones privadas:**
- `_verificar_estado_candado(carga)` — alerta por candado anómalo (solo flujo completo)
- `_verificar_exceso_litros(carga)` — alerta si litros > capacidad (ambos flujos)
- `_verificar_kilometraje_menor(carga)` — alerta si odómetro retrocede; omite si `kilometraje_actual == 0` (flujo LOCAL)
- `_procesar_ocr_candado_anterior(carga)` — OCR + `verificar_ciclo_candados()` (solo flujo completo)
- Flujo **LOCAL**: ejecuta solo `_verificar_exceso_litros` y `_verificar_kilometraje_menor`
- Al guardar `FotoCandadoNuevo` → `_procesar_ocr_foto_nueva()` → guarda `numero_candado`

**Servicio OCR (`config/services/ocr_service.py`):**
- `leer_numero_candado(imagen_field) → str` — extrae número de serie de un candado
- Backend **primario:** Google Cloud Vision API (`_leer_con_vision_api`) — usa `GOOGLE_VISION_API_KEY`
- Backend **fallback:** pytesseract local (`_leer_con_tesseract`) si Vision no disponible
- Pipeline pytesseract: escala de grises → contraste → nitidez → umbral binario → dos intentos (PSM 6 y PSM 8)
- Patrón extraído: `\d{4,}` (4 o más dígitos consecutivos)
- Funciona con imágenes locales y DigitalOcean Spaces (via `storage.open()`)
- Seguro si ningún backend está disponible (devuelve `''` con log)

**Servicio de ciclo (`combustible/services.py`):**
- `verificar_ciclo_candados(carga)` — compara `numero_candado_anterior` de la carga actual con los `numero_candado` de `FotoCandadoNuevo` de la carga anterior de la misma unidad → genera `AlertaCombustible(CANDADO_NO_COINCIDE)` si no coinciden

#### `AlertaCombustible`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `carga` | FK → CargaCombustible | Origen de la alerta |
| `tipo_alerta` | choices | `CANDADO_ALTERADO / CANDADO_VIOLADO / SIN_CANDADO / EXCESO_COMBUSTIBLE / CANDADO_NO_COINCIDE / KILOMETRAJE_MENOR` |
| `mensaje` | TextField | Descripción del problema |
| `resuelta` / `resuelta_por` / `fecha_resolucion` | | Control de resolución |

**Método `resolver(usuario)`:** Marca resuelta con usuario y timestamp.

**Context processor:** `alertas_combustible_pendientes` (solo superusuarios) inyectado en todos los templates vía `config/context_processors.py`.

#### `FotoCandadoNuevo`
- Permite múltiples fotos del candado nuevo por carga (relación 1:N)
- Campo `descripcion`: "Tanque 1", "Tanque 2", etc.
- Campos OCR: `numero_candado` (CharField), `ocr_procesado` (BooleanField)

**Despliegue DigitalOcean:** `apt.txt` en raíz instala `tesseract-ocr` y `tesseract-ocr-spa` automáticamente vía buildpack.

**Reporte Excel combustible:** columnas `candado_anterior` + `candado_nuevo_1`, `candado_nuevo_2`… (dinámicas según número de tanques).

**URLs:** 10 patrones
**Templates:** 11
- `wizard_paso1.html` — `wizard_paso6.html` (flujo completo, 6 archivos)
- `wizard_local_paso4.html` — paso 4 exclusivo para flujo LOCAL: sin resumen de tablero/candado, cromómetro y litros con colores verdes
- `carga_list.html`, `carga_detail.html`, `dashboard.html`, `alerta_list.html`

**Badge en Paso 1 (`wizard_paso1.html`):**
- Verde: "proceso simplificado (3 pasos)" — LOCAL sin `control_combustible_total`
- Naranja: "control total — proceso completo (6 pasos)" — LOCAL con `control_combustible_total = True`
- Azul: "proceso completo (6 pasos)" — FORÁNEO / ESPERANZA

---

### 5. `taller` — Órdenes de Trabajo del Taller

**Propósito:** Gestión completa del mantenimiento vehicular: diagnóstico, reparación, piezas y seguimiento del estado. Los costos se gestionan de forma externa (no se muestran en UI).

**Modelos:**

#### `TipoMantenimiento` — Catálogo
- Tipos: `PREVENTIVO / CORRECTIVO / PREDICTIVO`
- `kilometraje_sugerido` y `dias_sugeridos` para programación automática

#### `CategoriaFalla` — Catálogo
- Clasificación de problemas con `prioridad_default` (BAJA / MEDIA / ALTA / CRÍTICA)

#### `OrdenTrabajo` — Modelo principal
**Folio:** `OT-YYYYMMDD-XXX` (auto-generado en `save()`)

| Grupo | Campos |
|-------|--------|
| Identificación | `folio`, `unidad`, `operador_reporta` |
| Tipo | `tipo_mantenimiento`, `categoria_falla` |
| Problema | `descripcion_problema`, `sintomas`, `prioridad` |
| Tiempos | `fecha_creacion`, `fecha_programada`, `fecha_inicio_real`, `fecha_finalizacion` |
| Kilometraje | `kilometraje_ingreso`, `kilometraje_salida` |
| Asignación | `mecanico_asignado` (grupo "Mecánicos"), `supervisor` |
| Diagnóstico | `diagnostico`, `fecha_diagnostico` |
| Costos | `costo_estimado_mano_obra`, `costo_real_mano_obra` *(en modelo, no visibles en UI)* |
| Estado | `estado` (ver flujo abajo) |

**Flujo de estados:**
```
PENDIENTE → EN_DIAGNOSTICO → ESPERANDO_PIEZAS → EN_REPARACION → EN_PRUEBAS → COMPLETADA
                                                                              → CANCELADA
```

**Permisos custom:**
- `diagnosticar_orden`, `asignar_mecanico`, `aprobar_orden`, `cerrar_orden`

**Propiedades calculadas:**
- `costo_total_piezas_estimado` / `costo_total_piezas_real` *(en modelo, no en UI)*
- `costo_total_estimado` / `costo_total_real` *(en modelo, no en UI)*
- `dias_en_taller` / `horas_en_taller`
- `requiere_piezas` — hay piezas en estado PENDIENTE
- `kilometros_recorridos_en_taller`

**Métodos de transición:** `iniciar_diagnostico()`, `completar_diagnostico()`, `iniciar_reparacion()`, `completar()`, `cancelar()`

**`save()` override:** Al completarse actualiza `unidad.ultimo_mantenimiento`, `proximo_mantenimiento` y `kilometraje_actual`.

#### `PiezaRequerida`
- Estados: `PENDIENTE → SOLICITADA → EN_COMPRA → RECIBIDA → INSTALADA → CANCELADA`
- **Tres modos de captura** (excluyentes):
  1. `producto_almacen` (FK → `almacen.ProductoAlmacen`, nullable) — pieza encontrada en catálogo de almacén via buscador AJAX
  2. `producto` (FK → `compras.Producto`, nullable) — vínculo con catálogo de compras (auto-asignado si `producto_almacen` tiene `producto_compra`)
  3. `nombre_pieza` (CharField) — texto libre cuando la pieza no existe en almacén
- **Propiedades:**
  - `nombre_display` — retorna descripción del producto almacén, nombre del producto compras, o nombre libre (en ese orden)
  - `disponible_en_almacen` — `True` si `producto_almacen.cantidad >= cantidad`
- **Métodos:** `marcar_como_solicitada()`, `marcar_como_recibida()`, `marcar_como_instalada()`

**Flujo de surtido (vista `generar_requisicion`, un solo clic):**
- Piezas con `disponible_en_almacen=True` → crea `SolicitudSalida` (`SOL-XXXXXX`) en almacén
- Piezas sin stock o sin `producto_almacen` → crea `Requisicion` (`REQ-XXXXXX`) en compras; si es texto libre crea `compras.Producto` con `get_or_create`

**Buscador AJAX:** `GET /taller/api/buscar-producto-almacen/?q=texto` → JSON con hasta 10 resultados de `ProductoAlmacen` (id, descripcion, sku, cantidad, disponible)

#### `SeguimientoOrden`
- Bitácora de cambios de estado de la OT
- Archivos adjuntos (fotos, documentos del proceso)

#### `ChecklistMantenimiento` / `ChecklistOrden`
- Catálogo de ítems de revisión por `TipoMantenimiento`
- Instancias por orden con estados: `PENDIENTE / OK / REQUIERE_ATENCION / REPARADO / NO_APLICA`

#### `HistorialMantenimiento`
- Resumen consolidado por unidad, vinculado 1:1 a `OrdenTrabajo`
- Campos: `fecha_servicio`, `kilometraje_ingreso/salida`, `tipo_servicio`, `descripcion_breve`
- Métricas: `costo_total`, `tiempo_fuera_servicio_dias`, `tiempo_fuera_servicio_horas`

#### `ReporteFalla` — Reporte Público sin Login
**Folio:** `RF-YYYYMMDD-XXX` (auto-generado en `save()`)

| Campo | Descripción |
|-------|-------------|
| `unidad` | FK → Unidad |
| `operador_nombre` | Texto libre (quien reporta) |
| `categoria_falla` | FK → CategoriaFalla |
| `descripcion` | Descripción del problema |
| `foto` | ImageField (evidencia opcional) |
| `estado` | `NUEVO → EN_ATENCION → RESUELTO / CANCELADO` |
| `fecha_reporte` | Auto |
| `atendido_por` | FK → User (personal taller) |
| `notas_taller` | Respuesta / resolución |
| `orden_trabajo` | FK → OrdenTrabajo (opcional, si se escala) |

**Vistas públicas (sin `LoginRequiredMixin`):**
- `GET/POST /taller/reportar/<unidad_pk>/` — formulario de reporte, accesible sin autenticarse
- `GET /taller/reportar/enviado/<folio>/` — confirmación tras envío
- Ideal para imprimir QR por unidad y pegarlo en la cabina del vehículo

**Flujo de atención:**
1. Operador escanea QR → llena formulario → se crea `ReporteFalla(estado=NUEVO)`
2. Taller ve bandeja en `/taller/reportes/` → puede **atender**, **resolver**, **convertir a OT** o **cancelar**
3. Resolver directo → puede crear `AsignacionDirectaAlmacen` para piezas inmediatas
4. Convertir → crea `OrdenTrabajo` y vincula el reporte

**URLs QR:** `/taller/unidades/<unidad_pk>/qr/` (imprimible), `/taller/unidades/qr-todas/`

**Signals en `taller/signals.py`:**
- `notificar_nueva_orden` → email a grupo "Supervisores Taller"
- `notificar_cambio_estado_critico` → alerta si OT lleva >7 días; notifica al creador al completarse
- `asignar_mecanico_notificacion` → email al mecánico asignado
- `actualizar_estado_orden_por_piezas` → OT pasa a `ESPERANDO_PIEZAS` al agregar piezas
- `actualizar_piezas_recibidas` → al recibir `ItemRecepcion`, actualiza `PiezaRequerida` y puede pasar OT a `EN_REPARACION`

**Servicios en `taller/services.py`:**

`ServicioMantenimiento` — análisis predictivo de flota:
- `obtener_unidades_requieren_mantenimiento()` → lista de unidades por fecha vencida o km excedido
- `calcular_costo_total_mantenimiento(unidad, fecha_inicio, fecha_fin)` → suma histórica
- `calcular_estadisticas_unidad(unidad)` → dict completo: costos, tiempos promedio, frecuencia, eficiencia
- `obtener_unidades_en_taller()` → unidades con órdenes activas (no COMPLETADA/CANCELADA)
- `generar_pronostico_mantenimiento(unidad, meses=6)` → pronóstico basado en historial de km y periodicidad

`ReporteTaller` — reportes consolidados:
- `reporte_mensual(mes, anio)` → estadísticas de órdenes del mes (conteos, tiempos, categorías)
- `reporte_por_unidad(unidad, fecha_inicio, fecha_fin)` → detalle completo de OTs de una unidad
- `top_unidades_costosas(limite=10, fecha_inicio, fecha_fin)` → ranking por costo total

**URLs:** 20+ patrones
- Bandeja de reportes de falla: `/taller/reportes/`, `/taller/reportes/<folio>/`, `/taller/reportes/<folio>/atender/`, `/taller/reportes/<folio>/resolver/`, `/taller/reportes/<folio>/convertir-ot/`, `/taller/reportes/<folio>/cancelar/`
- QR por unidad: `/taller/unidades/<unidad_pk>/qr/`, `/taller/unidades/qr-todas/`
- APIs: `/taller/api/ordenes-activas/`, `/taller/api/buscar-producto-almacen/`

**UI — costos eliminados de templates:**
- `dashboard.html`: eliminadas tarjetas "Costo Estimado Activas" y "Costo Real (Mes)"; solo se muestra "Tiempo Promedio"
- `detalle_orden.html`: eliminadas sección "Costos Estimados / Costos Reales", campo "Costo Estimado MO" del form de diagnóstico, campo "Costo Real MO" del form de cambio de estado

---

### 6. `compras` — Gestión de Compras

**Propósito:** Flujo completo de adquisición: Requisición → Aprobación → Orden de Compra → Recepción en almacén.

**Modelos:**

#### `Proveedor` — Catálogo
- Campos: `nombre`, `rfc` (único), `direccion`, `telefono`, `email`, `contacto`

#### `Producto` — Catálogo
- Catálogo maestro de productos (usado también por taller)
- Campos: `nombre`, `descripcion`, `unidad_medida`, `categoria`
- Vinculado desde `almacen.ProductoAlmacen.producto_compra`

#### `Requisicion`
**Folio:** `REQ-YYYYMMDD-XXX`

**Flujo de estados:**
```
PENDIENTE → APROBADA → EN_COMPRA → COMPLETADA
          → RECHAZADA
          → CANCELADA
```

**Permisos custom:** `aprobar_requisicion`, `procesar_compra`, `gestionar_almacen`

**Métodos:** `aprobar(usuario, comentarios)`, `rechazar(usuario, comentarios)`

#### `ItemRequisicion`
- Línea de producto: `requisicion` + `producto` + `cantidad` + `descripcion_adicional`
- Referenciado desde `taller.PiezaRequerida.item_requisicion`

#### `OrdenCompra`
**Folio:** `OC-YYYYMMDD-XXX`

**Flujo de estados:**
```
PENDIENTE → ENVIADA → CONFIRMADA → EN_TRANSITO → RECIBIDA
                                              → CANCELADA
```

- Vincula `Requisicion` + `Proveedor`
- Datos de factura: `factura_numero`, `factura_fecha`, `factura_monto`, `factura_archivo`

#### `ItemOrdenCompra`
- Línea de la OC: `orden` + `item_requisicion` + `cantidad` + `precio_unitario`
- `subtotal` = `cantidad × precio_unitario`

#### `RecepcionAlmacen`
- Registro de recepción física: `orden_compra`, `recibido_por`, `ubicacion_almacen`
- Estados: `RECIBIDO / ALMACENADO / DISTRIBUIDO`
- Dispara signal en taller para actualizar `PiezaRequerida`

#### `ItemRecepcion`
- Control de cantidades: `cantidad_recibida`, `cantidad_aceptada`, `cantidad_rechazada`, `motivo_rechazo`

#### `Inventario`
- Control básico de stock por ubicación (legacy, ver `almacen.ProductoAlmacen` para control detallado)

**URLs:** 17 patrones
**Templates:** 27

---

### 7. `almacen` — Gestión de Almacén

**Propósito:** Control completo de inventario: entradas, salidas, trazabilidad, alertas automáticas y salidas rápidas de consumibles.

**Modelos:**

#### `ProductoAlmacen` — Catálogo maestro de inventario

| Campo | Descripción |
|-------|-------------|
| `sku` (unique) | Código interno del producto |
| `codigo_barras` | Opcional |
| `categoria` / `subcategoria` | Clasificación |
| `descripcion` | Nombre/descripción del producto |
| `localidad` | Ubicación física: "Pasillo A, Estante 3" |
| `cantidad` | Stock actual (actualizado por signals) |
| `unidad_medida` | Pieza / Litro / Kg / Caja / Metro |
| `stock_minimo` / `stock_maximo` | Umbrales de alerta y reorden |
| `costo_unitario` | Precio unitario |
| `tiene_caducidad` / `fecha_caducidad` | Control de vencimiento |
| `imagen` | Foto del producto (DigitalOcean Spaces) |
| `producto_compra` | FK → `compras.Producto` (vínculo catálogo) |
| `proveedor_principal` | FK → `compras.Proveedor` |
| `tiempo_reorden_dias` | Días estimados de reabastecimiento (default=7) |
| `es_consumible` | `True` para trapos, gasolina blanca, desengrasante, etc. |
| `activo` | Estado del producto |

**Propiedades calculadas:**
- `costo_total` = `cantidad × costo_unitario`
- `stock_bajo` — `cantidad ≤ stock_minimo`
- `stock_agotado` — `cantidad == 0`
- `stock_excedido` — `cantidad > stock_maximo`
- `proximo_caducar` — caduca en ≤30 días
- `caducado` — `fecha_caducidad < hoy`

**Índices:** `sku`, `codigo_barras`, `(categoria, subcategoria)`, `cantidad`, `fecha_caducidad`, `activo`

#### `EntradaAlmacen`
**Folio:** `ENT-YYYYMMDD-XXX`

**Tipos de entrada:**
- `FACTURA` — Producto nuevo con factura
- `TALLER_REPARADO` — Pieza reparada del taller
- `TALLER_RECICLADO` — Material para reciclar
- `AJUSTE` — Ajuste manual de inventario

Referencia opcional a `compras.OrdenCompra`, `taller.OrdenTrabajo` o `compras.RecepcionAlmacen`.

#### `ItemEntradaAlmacen`
- Detalle de productos: `producto_almacen`, `cantidad`, `costo_unitario`
- Trazabilidad: `lote`, `fecha_caducidad`, `ubicacion_asignada`
- **Signal:** Al crear un `ItemEntradaAlmacen` → aumenta `ProductoAlmacen.cantidad`

#### `SolicitudSalida`
**Folio:** `SOL-YYYYMMDD-XXX`

**Tipos:** `ORDEN_TRABAJO` / `SOLICITUD_GENERAL`

**Flujo de estados:**
```
PENDIENTE → AUTORIZADA → ENTREGADA (vía SalidaAlmacen)
          → RECHAZADA
          → CANCELADA
```

**Permiso custom:** `autorizar_salida_almacen`

Métodos: `autorizar(usuario)`, `rechazar(usuario, comentarios)`, `cancelar(motivo)`

#### `ItemSolicitudSalida`
- `cantidad_solicitada` / `cantidad_entregada`
- `cantidad_pendiente` y `entrega_completa` (propiedades)

#### `SalidaAlmacen`
**Folio:** `SAL-YYYYMMDD-XXX`

- Registro de entrega efectiva vinculada a `SolicitudSalida`
- `entregado_a` / `entregado_por` (ambos FK → User)
- **Signal:** Al crear `ItemSalidaAlmacen` → reduce `ProductoAlmacen.cantidad`

#### `ItemSalidaAlmacen`
- Trazabilidad: `lote`, `ubicacion_origen`

#### `MovimientoAlmacen` — Audit trail
- Registro inmutable de TODA variación de stock
- Tipos: `ENTRADA / SALIDA / AJUSTE / TRASLADO`
- Guarda `cantidad_anterior` y `cantidad_posterior` para auditoría completa

#### `AlertaStock` — Alertas automáticas
Generadas por signal al cambiar `ProductoAlmacen.cantidad`:

| Tipo | Disparador |
|------|-----------|
| `STOCK_MINIMO` | `cantidad ≤ stock_minimo` |
| `STOCK_AGOTADO` | `cantidad == 0` |
| `PROXIMO_CADUCAR` | Caduca en ≤30 días |
| `CADUCADO` | `fecha_caducidad < hoy` |

Método `resolver(usuario)` para cierre de alerta.

#### `SalidaRapidaConsumible`
**Folio:** `CON-YYYYMMDD-XXX`

- Salida express sin flujo de autorización
- Solo para productos con `es_consumible=True`
- Campos: `producto`, `cantidad`, `entregado_por`, `solicitante` (texto libre), `unidad` (FK → Unidad, nullable), `motivo`, `fecha_salida`
- **Signal:** Al crear → reduce `ProductoAlmacen.cantidad` directamente

#### `AsignacionDirectaAlmacen`
**Folio:** `ADI-YYYYMMDD-XXX`

- Asignación directa de piezas/productos a una unidad sin orden de taller
- Para reparaciones rápidas (focos, válvulas, etc.)
- Campos: `producto` (FK → ProductoAlmacen), `unidad` (FK → Unidad), `cantidad`, `motivo`, `observacion_interna` (solo superusuarios), `entregado_por`, `fecha_asignacion`

**URLs:** 29 patrones
**Templates:** 23

---

### 8. `reportes` — Reportes Configurables

**Propósito:** Generación y envío programado de reportes de almacén, combustible y taller; con historial de envíos auditado.

**Modelos:**

#### `ConfiguracionReporte`
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `nombre` | CharField | Nombre descriptivo |
| `modulo` | choices | `ALMACEN / COMBUSTIBLE / TALLER / UNIDADES` |
| `tipo_reporte` | choices | Tipo específico según módulo |
| `frecuencia` | choices | `DIARIO / SEMANAL / MENSUAL` |
| `dia_semana` | choices | Lunes–Domingo (para frecuencia SEMANAL) |
| `dia_mes` | IntegerField | 1-28 (para MENSUAL) |
| `destinatarios` | TextField | Emails separados por comas |
| `activo` | BooleanField | Habilita/deshabilita el reporte |
| `adjuntar_excel` | BooleanField | Incluye Excel en el correo |
| `ultimo_envio` | DateTimeField | Última vez que se ejecutó |
| `creado_por` | FK → User | |

**Métodos:** `get_destinatarios_list()` → lista de emails; `es_debido()` → `True` si corresponde ejecutar según frecuencia y `ultimo_envio`

#### `ReporteGenerado` — Historial de envíos
| Campo | Descripción |
|-------|-------------|
| `configuracion` | FK → ConfiguracionReporte |
| `fecha_generacion` | Timestamp |
| `periodo_inicio / periodo_fin` | Rango cubierto |
| `estado` | `GENERADO / ERROR / PARCIAL` |
| `destinatarios_enviados` | TextField |
| `resumen` | JSONField — datos clave del reporte |
| `mensaje_error` | Descripción si falló |

**Generadores modulares en `modulos/reportes/generadores/`:**

`almacen.py` — dict `GENERADORES` con:
- `ALMACEN_INVENTARIO` — snapshot completo del inventario
- `ALMACEN_STOCK_CRITICO` — productos con stock bajo o agotado
- `ALMACEN_CADUCIDAD` — próximos a vencer (≤30 días)
- `ALMACEN_MOVIMIENTOS` — historial de entradas/salidas del período

`combustible.py` — dict `GENERADORES` con:
- `COMBUSTIBLE_CARGAS` — todas las cargas del período
- `COMBUSTIBLE_CONSUMO` — consumo agregado por unidad
- `COMBUSTIBLE_ALERTAS` — alertas de candado generadas

`unidades.py` — dict `GENERADORES` con:
- `UNIDADES_KILOMETRAJE` — snapshot de kilometraje actual de todas las unidades activas (número económico, placa, kilometraje); KPIs: total unidades, km promedio, km máximo, unidad con mayor km

**Management command:** `python manage.py generar_reportes [--forzar-id N] [--dry-run]`
- Itera `ConfiguracionReporte` activas que `es_debido() == True`
- Llama al generador correspondiente del dict `GENERADORES`
- Genera Excel con openpyxl (estilos, colores) si `adjuntar_excel=True`
- Envía `EmailMultiAlternatives` (HTML + adjunto) vía SendGrid
- Registra resultado en `ReporteGenerado`
- `--forzar-id N`: ejecuta el reporte con id=N sin revisar frecuencia
- `--dry-run`: simula sin enviar ni guardar

**Vistas:**
- `ConfiguracionListView`, `CreateView`, `UpdateView`, `DeleteView`
- `HistorialReportesView`, `DetalleReporteGeneradoView`

**URLs:** 6 patrones
- `/reportes/configuraciones/`, `/reportes/configuraciones/nueva/`, `/reportes/configuraciones/<pk>/editar/`, `/reportes/configuraciones/<pk>/eliminar/`
- `/reportes/historial/`, `/reportes/historial/<pk>/`

**Template email:** `templates/reportes/email/reporte_base.html` — HTML para emails

---

## Servicios Externos

### `config/services/google_maps.py` — GoogleMapsService

Métodos disponibles:
- `calcular_distancia(cp_origen, cp_destino)` → `{success, distancia_km, duracion_min, distancia_texto, duracion_texto}`
- `batch_calcular_distancias(lista_destinos, cp_origen)` → procesamiento en lote
- `validar_codigo_postal(cp, pais)` → validación vía Geocoding API

Usado en:
- `BitacoraViaje.calcular_distancia_google()` — llamado manual desde la vista
- Endpoint AJAX en `bitacoras/urls.py`

---

## Sistema de Reportes Automáticos

> **Nota:** Existen dos sistemas de reportes paralelos:
> - **`config/reportes/`** — funciones legacy llamadas por APScheduler (proceso en Procfile)
> - **`modulos/reportes/`** — módulo con UI de configuración + management command (ver sección 8)

### `config/reportes/combustible.py` — `enviar_reporte_combustible()`
- Resumen: total cargas, litros, promedio del período
- Anomalías de candado detectadas
- Top 10 unidades por consumo
- Unidades que NO cargaron en el período
- Excel adjunto con 2 hojas: cargas detalladas + top unidades

### `config/reportes/almacen.py` — `enviar_reporte_almacen()`
- Resumen: salidas formales + salidas rápidas
- Top 10 productos más salidos
- Productos sin movimiento en 90 días
- Excel adjunto con 4 hojas: salidas almacén, salidas rápidas, estadísticas, resumen

### Scheduler (`config/scheduler.py` + `runscheduler.py`)
- Motor: APScheduler 3.11.2 + DjangoJobStore
- **Fix:** `job.next_run_time` usa `getattr` con fallback para compatibilidad con APScheduler 3.x y 4.x
- Configuración en `settings.REPORTES_CONFIG`:
  - `periodicidad`: `diario` / `semanal` / `mensual`
  - `hora`: HH:MM (default `08:00`)
  - `dia_semana`: e.g. `fri`
  - `dia_mes`: 1-28
- Comando: `python manage.py runscheduler` (proceso bloqueante, se configura como worker en Procfile)
- Comando de prueba: `python manage.py test_reportes`

---

## Dashboard Principal — `IndexView` (`config/views.py`)

Agrega métricas de TODOS los módulos en una sola consulta por sección:

| Sección | Métricas mostradas |
|---------|-------------------|
| **Operadores** | Total, activos |
| **Unidades** | Total, activas, próximo mantenimiento (≤7 días) |
| **Bitácoras** | Total, completados, en curso, del último mes, rendimiento promedio, velocidad promedio |
| **Combustible** | Cargas hoy, completadas, en proceso, alertas candado, litros hoy/mes, promedio/mes |
| **Taller** | OT pendientes, completadas este mes, unidades en taller, reportes de falla nuevos |
| **Compras** | Requisiciones pendientes, OC activas, proveedores activos |
| **Almacén** | Productos activos, stock bajo, alertas sin resolver, valor total inventario |

**Gráficas (datos para Chart.js):**
- Viajes por día (últimos 7 días)
- Combustible por día (litros, últimos 7 días)
- Estado de unidades (activas vs inactivas)
- Operadores por tipo (LOCAL / FORANEO / ESPERANZA)
- Top 5 categorías de almacén por valor
- Órdenes de taller por estado

---

## Sistema de Signals

| Signal | Módulo | Disparador | Efecto |
|--------|--------|-----------|--------|
| `post_save CargaCombustible` | combustible | `estado=COMPLETADO`, flujo LOCAL | Verifica exceso litros y `KILOMETRAJE_MENOR` (omite candado y OCR) |
| `post_save CargaCombustible` | combustible | `estado=COMPLETADO`, flujo FORANEO | Verifica candado, exceso litros, `KILOMETRAJE_MENOR`; OCR → `numero_candado_anterior` → `verificar_ciclo_candados()` → alerta `CANDADO_NO_COINCIDE` |
| `post_save FotoCandadoNuevo` | combustible | Creación | OCR → guarda `numero_candado` en la foto |
| `post_save OrdenTrabajo` | taller | Creación | Email a grupo "Supervisores Taller" |
| `post_save OrdenTrabajo` | taller | >7 días en taller | Email de alerta a supervisores/gerentes |
| `post_save OrdenTrabajo` | taller | Estado COMPLETADA | Email al creador |
| `post_save OrdenTrabajo` | taller | Cambio de mecánico | Email al mecánico |
| `post_save PiezaRequerida` | taller | Creación | OT pasa a ESPERANDO_PIEZAS |
| `post_save ItemRecepcion` | taller | Creación | Actualiza PiezaRequerida; si todo recibido → OT a EN_REPARACION |
| `post_save ItemEntradaAlmacen` | almacen | Creación | Aumenta stock de ProductoAlmacen |
| `post_save ItemSalidaAlmacen` | almacen | Creación | Reduce stock de ProductoAlmacen |
| `post_save SalidaRapidaConsumible` | almacen | Creación | Reduce stock de ProductoAlmacen |
| `post_save ProductoAlmacen` | almacen | Cambio de cantidad | Genera AlertaStock si aplica; crea MovimientoAlmacen |
| `post_delete *` | storage | Eliminación de modelo con archivo | Borra archivo de Spaces/local |
| `pre_save *` | storage | Actualización de archivo | Borra archivo anterior |

---

## Generación de Folios

Todos los folios se generan automáticamente en `save()` con el patrón `PREFIJO-YYYYMMDD-XXX`:

| Modelo | Prefijo | Ejemplo |
|--------|---------|---------|
| `Requisicion` | `REQ` | `REQ-20260227-001` |
| `OrdenCompra` | `OC` | `OC-20260227-001` |
| `OrdenTrabajo` | `OT` | `OT-20260227-001` |
| `EntradaAlmacen` | `ENT` | `ENT-20260227-001` |
| `SolicitudSalida` | `SOL` | `SOL-20260227-001` |
| `SalidaAlmacen` | `SAL` | `SAL-20260227-001` |
| `SalidaRapidaConsumible` | `CON` | `CON-20260227-001` |
| `AsignacionDirectaAlmacen` | `ADI` | `ADI-20260227-001` |
| `ReporteFalla` | `RF` | `RF-20260227-001` |

**Algoritmo:** Busca el `Max(folio)` del día → extrae sufijo numérico → incrementa → formato `{n:03d}`.

---

## Permisos Custom

| Permiso | App | Descripción |
|---------|-----|-------------|
| `aprobar_requisicion` | compras | Puede aprobar requisiciones |
| `procesar_compra` | compras | Puede procesar compras |
| `gestionar_almacen` | compras | Puede gestionar almacén |
| `diagnosticar_orden` | taller | Puede realizar diagnóstico |
| `asignar_mecanico` | taller | Puede asignar mecánicos |
| `aprobar_orden` | taller | Puede aprobar órdenes |
| `cerrar_orden` | taller | Puede cerrar órdenes |
| `autorizar_salida_almacen` | almacen | Puede autorizar salidas de almacén |

---

## Almacenamiento de Archivos

**`config/storage_backends.py`** selecciona backend según `USE_SPACES` en `.env`:

- **`USE_SPACES=True`:** DigitalOcean Spaces (SFO3, CDN activado)
  - URLs firmadas con expiración de 1 hora
  - Timestamp automático para evitar colisiones de nombre
- **`USE_SPACES=False`:** Filesystem local en `media/`

**Rutas de upload:**

| Tipo de archivo | Ruta |
|-----------------|------|
| Foto número económico combustible | `combustible/numero_economico/%Y/%m/` |
| Foto tablero combustible | `combustible/tablero/%Y/%m/` |
| Foto candado anterior | `combustible/candado_anterior/%Y/%m/` |
| Foto candado nuevo | `combustible/candado_nuevo/%Y/%m/` |
| Ticket / medidor | `combustible/tickets/%Y/%m/` |
| Imagen producto almacén | `almacen/productos/%Y/%m/` |
| Factura almacén | `almacen/facturas/%Y/%m/` |
| Seguimientos de taller | `taller/seguimientos/` |

---

## Relaciones Entre Módulos

```
operadores ──────────────────────────────────────┐
                                                 ▼
unidades ──── bitacoras ──── combustible         taller
    │                            │                 │
    │                        alertas           piezas ──── compras.Requisicion
    │                        combustible           │           │
    │                                          historial   compras.OrdenCompra
    └─── cargas_combustible                                    │
    │                                                     recepciones
    └─── ordenes_trabajo ─── almacen.SolicitudSalida          │
    │         │                   │                       almacen.EntradaAlmacen
    │     seguimientos         SalidaAlmacen
    │     checklist                │
    └─── SalidaRapidaConsumible  ItemSalidaAlmacen ──► ProductoAlmacen.cantidad
    │                                                       │
    └─── AsignacionDirectaAlmacen                      MovimientoAlmacen (audit)
                                                       AlertaStock (automática)
```

---

## Patrón de Navegación: Retorno a Página de Lista (`next`)

Todos los módulos con `UpdateView` y `DeleteView` implementan retorno a la misma página/filtro del listado de origen.

### Cómo funciona

**En el template de lista** — los links de editar y eliminar incluyen la URL actual codificada:
```html
<a href="{% url 'modulo:update' obj.pk %}?next={{ request.get_full_path|urlencode }}">Editar</a>
<a href="{% url 'modulo:delete' obj.pk %}?next={{ request.get_full_path|urlencode }}">Eliminar</a>
```

**En `views.py`** — `UpdateView` y `DeleteView` usan `get_success_url()`:
```python
def get_success_url(self):
    next_url = self.request.GET.get('next')
    if next_url:
        return next_url
    return reverse('modulo:list')
```

**En el template de formulario/confirmación** — botón Cancelar respeta `next`:
```html
<a href="{{ request.GET.next|default:'' }}{% if not request.GET.next %}{% url 'modulo:list' %}{% endif %}">
    Cancelar
</a>
```

### Beneficio
El parámetro `next` contiene la URL completa con todos los filtros activos y el número de página. Al guardar o cancelar, el usuario regresa exactamente al mismo estado del listado.

### Módulos con este patrón implementado
- `almacen` — `ProductoAlmacenUpdateView`, `ProductoAlmacenDeleteView`
- `operadores` — `OperadorUpdateView`, `OperadorDeleteView`
- `unidades` — `UnidadUpdateView`, `UnidadDeleteView`

---

## Comandos de Desarrollo

```bash
# Servidor de desarrollo
python manage.py runserver

# Migraciones
python manage.py makemigrations
python manage.py migrate

# Tests
python manage.py test                         # todos los módulos
python manage.py test modulos.almacen         # módulo específico

# Shell Django
python manage.py shell

# Comandos custom — datos iniciales
python manage.py load_operadores              # operadores: carga inicial desde datos
python manage.py load_unidades               # unidades: carga inicial desde datos
python manage.py cargar_productos_csv         # almacen: carga masiva de productos
python manage.py generar_checklist_default    # taller: crea ítems de checklist por defecto

# Reportes automáticos
python manage.py runscheduler                 # inicia scheduler (proceso bloqueante)
python manage.py test_reportes                # prueba manual de reportes
```

---

## Variables de Entorno (`.env`)

```bash
DEBUG=True
SECRET_KEY=...
DBURL=postgres://user:pass@host:port/db   # PostgreSQL en producción
GOOGLE_MAPS_API_KEY=...
GOOGLE_VISION_API_KEY=...                  # Google Cloud Vision para OCR de candados
EMAIL_HOST_PASSWORD=...                    # SendGrid API key
USE_SPACES=True/False
SPACES_ACCESS_KEY=...
SPACES_SECRET_KEY=...
SPACES_BUCKET_NAME=...
SPACES_REGION=sfo3
SPACES_CDN_ENDPOINT=...
```

---

## Producción

| Componente | Tecnología |
|-----------|-----------|
| WSGI | `gunicorn config.wsgi` (Procfile) |
| Archivos estáticos | WhiteNoise `CompressedManifestStaticFilesStorage` |
| Media | DigitalOcean Spaces (SFO3, CDN) |
| Email | SendGrid (SMTP backend) |
| Base de datos | PostgreSQL managed (DigitalOcean) vía `DBURL` |
| Despliegue | DigitalOcean App Platform |
| Reportes automáticos | APScheduler 3.11.2 + DjangoJobStore (worker en Procfile) |

---

## Dependencias Principales (`requirements.txt`)

```
Django==5.2.7
psycopg2-binary==2.9.11          # PostgreSQL
django-environ==0.12.0            # .env
django-storages==1.14.6           # S3/Spaces
boto3==1.41.5                     # AWS SDK
pillow==12.0.0                    # Imágenes
requests==2.32.5                  # HTTP (Google Maps)
openpyxl==3.1.5                   # Generación de Excel en reportes
django-template-maths==0.2.0      # Operaciones matemáticas en templates
pytesseract==0.3.13               # OCR para lectura de números de candado (requiere tesseract-ocr binario vía apt.txt)
apscheduler==3.11.2               # Scheduler de tareas
django-apscheduler==0.7.0         # Integración Django + APScheduler
sendgrid==6.12.5                  # Email transaccional
whitenoise                        # Static files (producción)
gunicorn                          # WSGI server
```

---

*Última actualización: 2026-03-18 (OCR Vision API + AlertaCombustible KILOMETRAJE_MENOR + ReporteFalla módulo taller + ServicioMantenimiento/ReporteTaller services + módulo reportes completo + RF- folio + GOOGLE_VISION_API_KEY)*
