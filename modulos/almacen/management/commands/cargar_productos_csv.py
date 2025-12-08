import csv
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from modulos.almacen.models import ProductoAlmacen


class Command(BaseCommand):
    help = 'Carga productos al almacén desde el archivo CSV InventarioKasuAlmacen.csv'

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_file',
            type=str,
            help='Ruta del archivo CSV a importar'
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='Actualizar productos existentes (basado en SKU)'
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        update_existing = options['update']
        
        self.stdout.write(self.style.SUCCESS(f'Iniciando carga desde: {csv_file}'))
        
        productos_creados = 0
        productos_actualizados = 0
        productos_error = 0
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                # Leer el CSV
                reader = csv.DictReader(file)
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 (1 is header)
                    try:
                        # Extraer datos del CSV
                        categoria = row.get('CATEGORÍA', '').strip()
                        subcategoria = row.get('SUBCATEGORÍA', '').strip()
                        sku = row.get('SKU', '').strip().upper()
                        codigo_barras = row.get('CÓDIGO DE BARRAS', '').strip()
                        descripcion = row.get('DESCRIPCION', '').strip()
                        cantidad_str = row.get('CANTIDAD', '0').strip()
                        unidad_medida = row.get('UdM', '').strip()
                        costo_unitario_str = row.get('COSTO UNITARIO (MXN)', '0').strip()
                        stock_min_str = row.get('Stock Min', '0').strip()
                        stock_max_str = row.get('Stock Max', '0').strip()
                        notas = row.get('NOTAS', '').strip()
                        
                        # Validar campos requeridos
                        if not sku or not descripcion:
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Fila {row_num}: SKU o DESCRIPCION vacíos, omitiendo...'
                                )
                            )
                            productos_error += 1
                            continue
                        
                        # Limpiar y convertir valores numéricos
                        cantidad = self._parse_decimal(cantidad_str)
                        costo_unitario = self._parse_decimal(costo_unitario_str)
                        stock_minimo = self._parse_decimal(stock_min_str)
                        stock_maximo = self._parse_decimal(stock_max_str) if stock_max_str else Decimal('0')
                        
                        # Limpiar código de barras (remover asteriscos si existen)
                        if codigo_barras:
                            codigo_barras = codigo_barras.replace('*', '').strip()
                            if not codigo_barras:
                                codigo_barras = None
                        else:
                            codigo_barras = None
                        
                        # Verificar si el producto ya existe
                        producto_existente = ProductoAlmacen.objects.filter(sku=sku).first()
                        
                        if producto_existente:
                            if update_existing:
                                # Actualizar producto existente
                                producto_existente.categoria = categoria
                                producto_existente.subcategoria = subcategoria
                                producto_existente.codigo_barras = codigo_barras
                                producto_existente.descripcion = descripcion
                                producto_existente.cantidad = cantidad
                                producto_existente.unidad_medida = unidad_medida
                                producto_existente.costo_unitario = costo_unitario
                                producto_existente.stock_minimo = stock_minimo
                                producto_existente.stock_maximo = stock_maximo
                                producto_existente.notas = notas
                                producto_existente.localidad = 'Almacén General'  # Default
                                producto_existente.save()
                                
                                productos_actualizados += 1
                                self.stdout.write(
                                    self.style.SUCCESS(f'✓ Actualizado: {sku} - {descripcion}')
                                )
                            else:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Fila {row_num}: Producto {sku} ya existe, omitiendo... '
                                        f'(use --update para actualizar)'
                                    )
                                )
                                productos_error += 1
                        else:
                            # Crear nuevo producto
                            producto = ProductoAlmacen.objects.create(
                                categoria=categoria,
                                subcategoria=subcategoria,
                                sku=sku,
                                codigo_barras=codigo_barras,
                                descripcion=descripcion,
                                localidad='Almacén General',  # Se puede ajustar manualmente después
                                cantidad=cantidad,
                                unidad_medida=unidad_medida,
                                stock_minimo=stock_minimo,
                                stock_maximo=stock_maximo,
                                costo_unitario=costo_unitario,
                                notas=notas,
                                activo=True
                            )
                            
                            productos_creados += 1
                            self.stdout.write(
                                self.style.SUCCESS(f'✓ Creado: {sku} - {descripcion}')
                            )
                    
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'✗ Error en fila {row_num}: {str(e)}'
                            )
                        )
                        productos_error += 1
                        continue
        
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f'Archivo no encontrado: {csv_file}')
            )
            return
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error al leer el archivo: {str(e)}')
            )
            return
        
        # Resumen final
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS('RESUMEN DE IMPORTACIÓN'))
        self.stdout.write('='*60)
        self.stdout.write(f'Productos creados:     {productos_creados}')
        self.stdout.write(f'Productos actualizados: {productos_actualizados}')
        self.stdout.write(f'Productos con error:   {productos_error}')
        self.stdout.write(f'Total procesados:      {productos_creados + productos_actualizados + productos_error}')
        self.stdout.write('='*60 + '\n')
        
        if productos_creados > 0 or productos_actualizados > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    '¡Importación completada exitosamente!'
                )
            )
    
    def _parse_decimal(self, value):
        """Convierte string con formato de moneda a Decimal"""
        if not value:
            return Decimal('0')
        
        # Remover caracteres no numéricos excepto punto y coma
        cleaned = value.replace('$', '').replace(',', '').strip()
        
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return Decimal('0')
