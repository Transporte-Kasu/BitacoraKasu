# Plan: OCR de Números de Candado en Cargas de Combustible

**Fecha:** 2026-03-05
**Estado:** IMPLEMENTADO

---

## Objetivo

Leer automáticamente los números de serie de los candados a partir de las fotos
ya capturadas en el proceso de carga de combustible, almacenarlos como datos
independientes y verificar la continuidad del ciclo:

> Los candados **nuevos** de una carga deben coincidir con los candados
> **anteriores** de la siguiente carga de la misma unidad.

No se modifica ningún template existente.

---

## Contexto del modelo actual

```
CargaCombustible
├── foto_candado_anterior   (ImageField)  ← 1 foto del candado que se retira
├── foto_candado_nuevo      (ImageField)  ← foto legacy (puede estar vacía)
└── fotos_candado_nuevo     (FK→ FotoCandadoNuevo, 1:N)  ← fotos individuales por tanque
        ├── foto
        └── descripcion  "Tanque 1", "Tanque 2", …

AlertaCombustible
└── tipo_alerta: CANDADO_ALTERADO | CANDADO_VIOLADO | SIN_CANDADO | EXCESO_COMBUSTIBLE
```

---

## Cambios de modelo

### 1. `CargaCombustible` — agregar campo

```python
numero_candado_anterior = models.CharField(
    max_length=50,
    blank=True,
    verbose_name="Número de candado anterior",
    help_text="Extraído por OCR de foto_candado_anterior"
)
ocr_candado_anterior_ok = models.BooleanField(
    default=False,
    verbose_name="OCR candado anterior procesado"
)
```

### 2. `FotoCandadoNuevo` — agregar campos

```python
numero_candado = models.CharField(
    max_length=50,
    blank=True,
    verbose_name="Número de candado",
    help_text="Extraído por OCR de la foto"
)
ocr_procesado = models.BooleanField(
    default=False,
    verbose_name="OCR procesado"
)
```

### 3. `AlertaCombustible` — nuevo tipo

```python
('CANDADO_NO_COINCIDE', 'Candado no coincide con carga anterior'),
```

### Migración requerida

```
python manage.py makemigrations combustible
python manage.py migrate
```

---

## Servicio OCR (`config/services/ocr_service.py`)

Módulo independiente con interfaz clara; el backend se puede cambiar
sin tocar el resto del código.

```python
class OCRService:
    """Extrae texto/números de imágenes."""

    @staticmethod
    def leer_numero_candado(imagen_field) -> str:
        """
        Recibe un ImageField de Django.
        Devuelve el número encontrado o '' si no se puede leer.
        """
        ...
```

### Backends a evaluar (en orden de preferencia)

| Backend | Ventaja | Desventaja |
|---------|---------|------------|
| **Google Cloud Vision API** | Alta precisión, ya tiene billing activo (Maps) | Costo por imagen (~$1.50/1000 imgs) |
| **pytesseract** | Gratis, on-premise | Requiere Tesseract binario en servidor; precisión media en fotos de campo |
| **easyocr** | Buena precisión, sin API externa | Dependencia pesada (~500 MB), lenta en CPU |
| **Azure Computer Vision** | Alta precisión | Cuenta adicional |

**Recomendación:** Google Cloud Vision (misma cuenta que Maps API).
Para desarrollo local: pytesseract como fallback.

```python
# config/services/ocr_service.py
import re
from django.conf import settings

class OCRService:
    @staticmethod
    def leer_numero_candado(imagen_field) -> str:
        if getattr(settings, 'USE_GOOGLE_VISION', False):
            return OCRService._google_vision(imagen_field)
        return OCRService._pytesseract(imagen_field)

    @staticmethod
    def _google_vision(imagen_field) -> str:
        """Llama a Google Cloud Vision API."""
        ...

    @staticmethod
    def _pytesseract(imagen_field) -> str:
        """Fallback local con pytesseract."""
        import pytesseract
        from PIL import Image
        img = Image.open(imagen_field)
        texto = pytesseract.image_to_string(img, config='--psm 6')
        numeros = re.findall(r'[A-Z0-9]{4,}', texto.upper())
        return numeros[0] if numeros else ''
```

---

## Flujo de procesamiento OCR

El OCR **no bloquea** el proceso de carga. Se ejecuta de forma asíncrona
(management command / tarea programada), o de forma síncrona en el signal
`post_save` si la imagen ya está disponible.

### Opción A — Signal post_save (simple, síncrono)

```
FotoCandadoNuevo.post_save
    → si ocr_procesado == False
    → OCRService.leer_numero_candado(foto)
    → guardar numero_candado + ocr_procesado=True
    → verificar_ciclo_candados(carga)

CargaCombustible.post_save  (cuando estado → COMPLETADO)
    → si ocr_candado_anterior_ok == False
    → OCRService.leer_numero_candado(foto_candado_anterior)
    → guardar numero_candado_anterior + ocr_candado_anterior_ok=True
    → verificar_ciclo_candados(self)
```

### Opción B — Management command (recomendado para producción)

```bash
python manage.py procesar_ocr_candados [--id <carga_id>] [--dry-run]
```

- Busca cargas con `ocr_candado_anterior_ok=False` o fotos con `ocr_procesado=False`
- Procesa en lote
- Se ejecuta via scheduler (mismo cron que los reportes)

**Para implementación inicial: Opción A** (más simple, sin infraestructura extra).

---

## Lógica de verificación de ciclo

Función en `combustible/services.py` (nuevo archivo):

```python
def verificar_ciclo_candados(carga: CargaCombustible):
    """
    Compara los números de candado nuevo de la carga anterior
    con el número de candado anterior de la carga actual.
    Genera AlertaCombustible si no coinciden.
    """
    # 1. Obtener carga anterior completada de la misma unidad
    carga_anterior = (
        CargaCombustible.objects
        .filter(unidad=carga.unidad, estado='COMPLETADO')
        .exclude(pk=carga.pk)
        .order_by('-fecha_hora_inicio')
        .prefetch_related('fotos_candado_nuevo')
        .first()
    )
    if not carga_anterior:
        return  # Primera carga de la unidad

    # 2. Números de candados nuevos de la carga anterior
    numeros_nuevos_anterior = set(
        foto.numero_candado
        for foto in carga_anterior.fotos_candado_nuevo.all()
        if foto.numero_candado
    )
    if not numeros_nuevos_anterior:
        return  # Sin datos OCR de la carga anterior

    # 3. Número del candado que se retiró en la carga actual
    numero_anterior_actual = carga.numero_candado_anterior
    if not numero_anterior_actual:
        return  # Sin datos OCR del candado retirado

    # 4. Comparar
    if numero_anterior_actual not in numeros_nuevos_anterior:
        AlertaCombustible.objects.get_or_create(
            carga=carga,
            tipo_alerta='CANDADO_NO_COINCIDE',
            defaults={
                'mensaje': (
                    f"El candado retirado ({numero_anterior_actual}) no coincide "
                    f"con los candados colocados en la carga anterior "
                    f"({', '.join(numeros_nuevos_anterior)})."
                )
            }
        )
```

---

## Representación de datos en el Excel de reportes

En `generar_cargas_periodo` (ya existe en `modulos/reportes/generadores/combustible.py`)
se agregan las columnas sin romper nada:

```python
# Números de candados nuevos (puede haber 2 o más)
fotos_nuevos = list(c.fotos_candado_nuevo.all())
for i, foto in enumerate(fotos_nuevos, 1):
    fila[f'candado_nuevo_{i}'] = foto.numero_candado or 'Sin OCR'

filas.append({
    ...
    'candado_anterior': c.numero_candado_anterior or 'Sin OCR',
    # candado_nuevo_1, candado_nuevo_2, etc. — dinámicos
    **{f'candado_nuevo_{i}': (foto.numero_candado or 'Sin OCR')
       for i, foto in enumerate(fotos_candado_nuevo, 1)},
})
```

> El Excel ya soporta columnas dinámicas porque `_generar_excel` usa las
> `keys()` del primer dict de `filas` como encabezados.

---

## Estructura de archivos nuevos/modificados

```
config/
└── services/
    └── ocr_service.py              ← NUEVO

modulos/combustible/
├── models.py                       ← MODIFICAR: nuevos campos + tipo alerta
├── migrations/XXXX_ocr_campos.py   ← NUEVO (auto-generada)
├── services.py                     ← NUEVO: verificar_ciclo_candados()
├── signals.py                      ← MODIFICAR: llamar OCR en post_save
└── management/commands/
    └── procesar_ocr_candados.py    ← NUEVO (opcional, opción B)

modulos/reportes/generadores/
└── combustible.py                  ← MODIFICAR: agregar columnas candados al Excel
```

---

## Dependencias nuevas

```
# requirements.txt — agregar según backend elegido

# Opción pytesseract (fallback local)
pytesseract==0.3.13
Pillow>=12.0.0          # ya instalado

# Opción Google Vision (recomendado producción)
google-cloud-vision==3.7.2
```

Sistema operativo (producción / DigitalOcean):
- pytesseract requiere: `apt-get install tesseract-ocr`
- Google Vision: solo librería Python, sin binario

---

## Variable de entorno nueva

```bash
# .env
USE_GOOGLE_VISION=True   # False → usa pytesseract
GOOGLE_VISION_API_KEY=... # o usar Application Default Credentials
```

---

## Orden de implementación (pasos)

| # | Tarea | Archivo |
|---|-------|---------|
| 1 | Agregar campos al modelo `CargaCombustible` y `FotoCandadoNuevo` | `combustible/models.py` |
| 2 | Agregar tipo `CANDADO_NO_COINCIDE` a `AlertaCombustible` | `combustible/models.py` |
| 3 | Generar y aplicar migración | — |
| 4 | Crear `OCRService` con backend configurable | `config/services/ocr_service.py` |
| 5 | Crear función `verificar_ciclo_candados` | `combustible/services.py` |
| 6 | Agregar signals OCR en `post_save` | `combustible/signals.py` |
| 7 | Actualizar Excel del reporte con columnas de candados | `modulos/reportes/generadores/combustible.py` |
| 8 | (Opcional) Management command para procesar OCR en lote | `combustible/management/commands/` |
| 9 | Instalar dependencias + variable de entorno | `requirements.txt`, `.env` |

---

## Consideraciones de calidad OCR

Las fotos de campo (mala iluminación, ángulo, suciedad) reducen la precisión.
Se recomienda:

- Guardar el texto crudo del OCR en un campo `ocr_raw` para auditoría
- Permitir **corrección manual** del número vía Django Admin (campo editable)
- No bloquear el flujo de carga si el OCR falla — simplemente queda en blanco
- En el Excel mostrar `"Sin OCR"` cuando el campo está vacío

---

## No se modifica

- Ningún template HTML (`templates/combustible/`)
- Ninguna URL existente
- El flujo de carga en 5 pasos
- Las alertas existentes (CANDADO_ALTERADO, CANDADO_VIOLADO, SIN_CANDADO, EXCESO_COMBUSTIBLE)
- El panel de alertas visible en la navbar

---

*Plan generado: 2026-03-05*
