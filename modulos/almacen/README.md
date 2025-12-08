# Módulo de Almacén

Sistema completo de gestión de almacén que controla inventario, entradas, salidas, y alertas automáticas.

## Características Principales

### 1. Gestión de Productos
- Catálogo completo con SKU único y código de barras
- Categorías y subcategorías
- Control de stock (mínimo, máximo, actual)
- Gestión de caducidad
- Costos y ubicación física
- Integración con módulo de compras

### 2. Entradas de Almacén
Tipos de entrada:
- **FACTURA**: Productos nuevos desde órdenes de compra
- **TALLER_REPARADO**: Piezas reparadas del taller
- **TALLER_RECICLADO**: Piezas/materiales para reciclar
- **AJUSTE**: Ajustes manuales de inventario

Cada entrada genera automáticamente:
- Folio único (ENT-YYYYMMDD-XXX)
- Movimientos de almacén
- Actualización de stock
- Verificación de alertas

### 3. Solicitudes de Salida
Flujo de autorización:
1. Solicitud creada (folio SOL-YYYYMMDD-XXX)
2. Autorización por gerencia (para solicitudes generales)
3. Procesamiento de entrega
4. Generación de salida (folio SAL-YYYYMMDD-XXX)

Tipos de solicitud:
- **ORDEN_TRABAJO**: Para órdenes de trabajo del taller
- **SOLICITUD_GENERAL**: Requiere autorización de gerencia

### 4. Alertas Automáticas
Generación automática de alertas por:
- Stock mínimo alcanzado
- Stock agotado
- Productos próximos a caducar (30 días)
- Productos caducados

### 5. Trazabilidad Completa
- Historial de movimientos por producto
- Registro de entradas y salidas
- Lotes y fechas de caducidad
- Ubicaciones físicas

## Modelos

### ProductoAlmacen
Catálogo de productos con control de stock.

**Campos principales:**
- `sku`: Código único del producto
- `codigo_barras`: Código de barras (opcional)
- `categoria`, `subcategoria`: Clasificación
- `descripcion`: Descripción del producto
- `localidad`: Ubicación física en almacén
- `cantidad`: Stock actual
- `unidad_medida`: Unidad (Pieza, Litro, Kg, etc.)
- `stock_minimo`, `stock_maximo`: Umbrales de stock
- `costo_unitario`: Costo por unidad
- `tiene_caducidad`, `fecha_caducidad`: Control de caducidad
- `imagen`: Imagen del producto

**Relaciones:**
- `producto_compra`: FK a compras.Producto
- `proveedor_principal`: FK a compras.Proveedor

**Properties calculados:**
- `costo_total`: cantidad × costo_unitario
- `stock_bajo`, `stock_agotado`: Verificaciones de stock
- `proximo_caducar`, `caducado`: Verificaciones de caducidad

### EntradaAlmacen
Registro de entradas al almacén.

**Campos principales:**
- `folio`: Auto-generado (ENT-YYYYMMDD-XXX)
- `tipo`: FACTURA, TALLER_REPARADO, TALLER_RECICLADO, AJUSTE
- `fecha_entrada`: Fecha y hora
- `recibido_por`: Usuario que recibe

**Referencias:**
- `orden_compra`: FK a compras.OrdenCompra (para tipo FACTURA)
- `orden_trabajo`: FK a taller.OrdenTrabajo (para tipo TALLER)

### SolicitudSalida
Solicitudes de salida de productos.

**Campos principales:**
- `folio`: Auto-generado (SOL-YYYYMMDD-XXX)
- `tipo`: ORDEN_TRABAJO, SOLICITUD_GENERAL
- `estado`: PENDIENTE, AUTORIZADA, RECHAZADA, ENTREGADA, CANCELADA
- `solicitante`: Usuario que solicita
- `justificacion`: Motivo de la solicitud

**Autorización:**
- `requiere_autorizacion`: Boolean (True para SOLICITUD_GENERAL)
- `autorizado_por`, `fecha_autorizacion`, `comentarios_autorizacion`

**Métodos:**
- `autorizar(usuario, comentarios)`: Autorizar solicitud
- `rechazar(usuario, comentarios)`: Rechazar solicitud
- `cancelar(motivo)`: Cancelar solicitud

### SalidaAlmacen
Registro de salidas efectivas.

**Campos principales:**
- `folio`: Auto-generado (SAL-YYYYMMDD-XXX)
- `solicitud_salida`: FK a SolicitudSalida
- `fecha_salida`: Fecha y hora
- `entregado_a`, `entregado_por`: Usuarios involucrados

### MovimientoAlmacen
Historial completo de movimientos.

**Campos principales:**
- `tipo`: ENTRADA, SALIDA, AJUSTE, TRASLADO
- `producto_almacen`: FK a ProductoAlmacen
- `cantidad`: Cantidad del movimiento (+ entrada, - salida)
- `cantidad_anterior`, `cantidad_posterior`: Para trazabilidad
- `entrada_almacen`, `salida_almacen`: Referencias opcionales
- `usuario`: Usuario que realizó el movimiento

### AlertaStock
Alertas automáticas de inventario.

**Tipos de alerta:**
- `STOCK_MINIMO`: Stock alcanzó el mínimo
- `STOCK_AGOTADO`: Stock en cero
- `PROXIMO_CADUCAR`: Caducidad en 30 días
- `CADUCADO`: Producto caducado

**Campos:**
- `producto_almacen`: FK a ProductoAlmacen
- `tipo_alerta`, `mensaje`: Tipo y descripción
- `fecha_generacion`, `fecha_resolucion`: Fechas
- `resuelta`, `resuelta_por`: Estado de resolución

## Signals

### Actualización automática de stock
- **post_save de ItemEntradaAlmacen**: Incrementa stock y crea movimiento
- **post_save de ItemSalidaAlmacen**: Reduce stock y crea movimiento

### Generación de alertas
- **post_save de ProductoAlmacen**: Verifica y genera alertas automáticamente

### Actualización de solicitudes
- **post_save de SalidaAlmacen**: Actualiza estado de la solicitud

## Vistas Principales

### Dashboard (`/almacen/`)
Vista principal con:
- Estadísticas generales
- Alertas activas
- Solicitudes pendientes
- Valor del inventario
- Productos próximos a caducar
- Movimientos recientes

### Productos
- Lista con filtros (categoría, SKU, stock bajo, caducidad)
- Detalle con historial de movimientos y alertas
- Crear, editar, eliminar

### Entradas
- Lista con filtros (tipo, fechas)
- Detalle con items
- Crear entrada

### Solicitudes
- Lista con filtros (tipo, estado, fechas)
- Detalle con items y flujo de autorización
- Crear solicitud
- Autorizar/rechazar (requiere permission)
- Procesar entrega

### Salidas
- Lista de salidas
- Detalle con items entregados

### Reportes
- Inventario actual
- Stock crítico
- Productos próximos a caducar

## Permisos

### almacen.autorizar_salida_almacen
Permite autorizar o rechazar solicitudes de salida del almacén.

## Integración con otros módulos

### Con Compras
- `ProductoAlmacen.producto_compra`: Vincula con catálogo de compras
- `EntradaAlmacen.orden_compra`: Entrada desde orden de compra
- Compatible con `RecepcionAlmacen` existente

### Con Taller
- `SolicitudSalida.orden_trabajo`: Salida para orden de trabajo
- `EntradaAlmacen.orden_trabajo`: Entrada de piezas reparadas/recicladas
- Actualización automática de `PiezaRequerida`

## Flujo de Trabajo

### Entrada de productos nuevos (Factura)
1. Crear `EntradaAlmacen` tipo FACTURA con `orden_compra`
2. Agregar items (`ItemEntradaAlmacen`)
3. El signal actualiza stock automáticamente
4. Se generan movimientos de almacén
5. Se verifican alertas

### Salida para orden de trabajo
1. Crear `SolicitudSalida` tipo ORDEN_TRABAJO
2. Agregar items solicitados
3. (Opcional) Autorizar solicitud
4. Procesar entrega (crea `SalidaAlmacen`)
5. El signal reduce stock y genera movimientos
6. Actualiza estado de la solicitud

### Entrada de piezas reparadas
1. Crear `EntradaAlmacen` tipo TALLER_REPARADO con `orden_trabajo`
2. Agregar items
3. Stock se actualiza automáticamente

## URLs Principales

```
/almacen/                                      - Dashboard
/almacen/productos/                            - Lista de productos
/almacen/productos/crear/                      - Crear producto
/almacen/productos/<id>/                       - Detalle producto
/almacen/entradas/                             - Lista de entradas
/almacen/entradas/crear/                       - Crear entrada
/almacen/solicitudes/                          - Lista de solicitudes
/almacen/solicitudes/crear/                    - Crear solicitud
/almacen/solicitudes/<id>/autorizar/           - Autorizar/rechazar
/almacen/solicitudes/<id>/procesar-entrega/    - Procesar entrega
/almacen/salidas/                              - Lista de salidas
/almacen/movimientos/                          - Historial de movimientos
/almacen/alertas/                              - Lista de alertas
/almacen/reportes/inventario/                  - Reporte de inventario
/almacen/reportes/stock-critico/               - Reporte stock crítico
/almacen/reportes/proximos-caducar/            - Reporte caducidad
```

## Validaciones

### ProductoAlmacen
- SKU único (convertido a mayúsculas)
- Si `tiene_caducidad=True`, `fecha_caducidad` es obligatoria
- `stock_maximo` debe ser mayor que `stock_minimo`

### EntradaAlmacen
- Tipo FACTURA requiere `orden_compra`
- Tipo TALLER requiere `orden_trabajo`

### SolicitudSalida
- Tipo ORDEN_TRABAJO requiere `orden_trabajo`
- SOLICITUD_GENERAL siempre requiere autorización
- Solo se puede entregar si estado = AUTORIZADA

### ItemSalidaAlmacen
- Validar stock disponible
- No exceder cantidad solicitada

## Testing

Ejecutar tests:
```bash
python manage.py test modulos.almacen
```

Los tests incluyen:
- Creación de productos y cálculos
- Métodos de agregar/reducir stock
- Generación de folios
- Flujo de autorización
- Generación automática de alertas

## Admin

Todos los modelos están registrados en el admin de Django con:
- Filtros por campos relevantes
- Búsqueda
- Inlines para modelos relacionados
- Fieldsets organizados

## Próximos Pasos

Para completar el módulo, se requiere:
1. Crear templates HTML para todas las vistas
2. Implementar integración automática con RecepcionAlmacen de compras
3. Implementar actualización de PiezaRequerida en taller
4. Agregar exportación de reportes (CSV, Excel, PDF)
5. Implementar códigos de barras escaneables
6. Dashboard con gráficas de stock y movimientos
