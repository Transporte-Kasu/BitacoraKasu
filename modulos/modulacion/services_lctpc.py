"""
Parser del adjunto de programación de citas de LCTPC.

El adjunto llega como `.xls` pero es una **tabla HTML** (ISO-8859-1), con:
  - una celda título `class="oscuro"` con "... para el <día> <mes> <año>"
    (mes en inglés o español), y
  - una tabla con columnas
    CONTENEDOR | TRANSPORTISTA | FOLIO | VENTANA DE REGISTRO | HORARIO DE CITA.

Este módulo es puro: no toca la BD ni la red.
"""
import datetime
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup


class ErrorParseoLCTPC(Exception):
    """El adjunto o el asunto no tienen el formato esperado."""


@dataclass
class RenglonLCTPC:
    contenedor: str
    transportista: str
    folio_lctpc: str
    registro_inicio: datetime.time
    registro_fin: datetime.time
    cita_inicio: datetime.time
    cita_fin: datetime.time
    tipo_cita: str = ''
    grupo_cita: str = ''


@dataclass
class ProgramacionParseada:
    fecha: datetime.date
    fecha_titulo_excel: datetime.date | None
    fecha_asunto: datetime.date | None
    renglones: list
    avisos: list = field(default_factory=list)


_MESES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11,
    'diciembre': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11,
    'december': 12,
}
_FECHA_RE = re.compile(
    r'para el\s+(\d{1,2})\s+([A-Za-zÀ-ſ]+)\s+(\d{4})', re.IGNORECASE
)
_RANGO_RE = re.compile(r'^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$')


def _parsear_fecha_texto(texto):
    if not texto:
        return None
    m = _FECHA_RE.search(texto)
    if not m:
        return None
    mes = _MESES.get(m.group(2).lower())
    if not mes:
        return None
    try:
        return datetime.date(int(m.group(3)), mes, int(m.group(1)))
    except ValueError:
        return None


def _parsear_rango(texto):
    m = _RANGO_RE.match(texto or '')
    if not m:
        raise ErrorParseoLCTPC(f'Rango horario inválido: {texto!r}')
    h1, m1, h2, m2 = (int(x) for x in m.groups())
    try:
        return datetime.time(h1, m1), datetime.time(h2, m2)
    except ValueError as exc:
        raise ErrorParseoLCTPC(f'Rango horario inválido: {texto!r}') from exc


def _encontrar_tabla_datos(soup):
    for tabla in soup.find_all('table'):
        encabezados = [c.get_text(strip=True).upper() for c in tabla.find_all('th')]
        if 'CONTENEDOR' in encabezados:
            return tabla
    return None


def parsear_programacion(contenido: bytes, asunto: str) -> ProgramacionParseada:
    soup = BeautifulSoup(contenido.decode('iso-8859-1'), 'html.parser')

    titulo_cell = soup.find('th', class_='oscuro')
    fecha_titulo = _parsear_fecha_texto(
        titulo_cell.get_text(strip=True) if titulo_cell else ''
    )
    fecha_asunto = _parsear_fecha_texto(asunto or '')

    avisos = []
    if fecha_asunto and fecha_titulo and fecha_asunto != fecha_titulo:
        avisos.append(
            f'La fecha del asunto ({fecha_asunto}) no coincide con la del Excel '
            f'({fecha_titulo}); se usa la del asunto.'
        )
    fecha = fecha_asunto or fecha_titulo
    if fecha is None:
        raise ErrorParseoLCTPC(
            'No se pudo determinar la fecha de modulación (ni en el asunto ni en el Excel).'
        )

    tabla = _encontrar_tabla_datos(soup)
    if tabla is None:
        raise ErrorParseoLCTPC('No se encontró la tabla de contenedores en el adjunto.')

    renglones = []
    for tr in tabla.find_all('tr'):
        celdas = tr.find_all('td')
        if len(celdas) < 5:
            continue
        vals = [c.get_text(strip=True) for c in celdas]
        contenedor, transportista, folio, ventana, cita = vals[:5]
        reg_ini, reg_fin = _parsear_rango(ventana)
        cita_ini, cita_fin = _parsear_rango(cita)
        renglones.append(RenglonLCTPC(
            contenedor=contenedor.strip().upper(),
            transportista=transportista.strip(),
            folio_lctpc=folio.strip(),
            registro_inicio=reg_ini,
            registro_fin=reg_fin,
            cita_inicio=cita_ini,
            cita_fin=cita_fin,
        ))

    if not renglones:
        raise ErrorParseoLCTPC('La tabla del adjunto no tiene renglones de datos.')

    return ProgramacionParseada(
        fecha=fecha,
        fecha_titulo_excel=fecha_titulo,
        fecha_asunto=fecha_asunto,
        renglones=renglones,
        avisos=avisos,
    )
