import requests
import os


class GoogleMapsService:
    """
    Servicio para interactuar con Google Maps API
    Maneja cálculos de distancia y duración
    Ubicación: core/services/google_maps.py
    """
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get('GOOGLE_MAPS_API_KEY')
        self.base_url = 'https://maps.googleapis.com/maps/api/distancematrix/json'
    
    def calcular_distancia(self, cp_origen, cp_destino):
        """
        Calcula distancia entre dos códigos postales
        
        Args:
            cp_origen (str): Código postal de origen
            cp_destino (str): Código postal de destino
        
        Returns:
            dict: Resultado con distancia y duración
        """
        if not self.api_key:
            return {
                'success': False,
                'error': 'API key no configurada'
            }
        
        try:
            params = {
                'origins': f'{cp_origen},Mexico',
                'destinations': f'{cp_destino},Mexico',
                'key': self.api_key,
                'units': 'metric',
                'language': 'es'
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            data = response.json()
            
            if data['status'] == 'OK':
                elemento = data['rows'][0]['elements'][0]
                
                if elemento['status'] == 'OK':
                    return {
                        'success': True,
                        'distancia_km': elemento['distance']['value'] / 1000,
                        'duracion_min': elemento['duration']['value'] / 60,
                        'distancia_texto': elemento['distance']['text'],
                        'duracion_texto': elemento['duration']['text'],
                        'origen_formateado': data.get('origin_addresses', [''])[0],
                        'destino_formateado': data.get('destination_addresses', [''])[0]
                    }
                else:
                    return {
                        'success': False,
                        'error': f"No se pudo calcular la ruta: {elemento['status']}"
                    }
            else:
                return {
                    'success': False,
                    'error': f"Error en la API: {data['status']}"
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Error: {str(e)}"
            }
    
    def batch_calcular_distancias(self, lista_destinos, cp_origen='40812'):
        """
        Calcula distancias para múltiples destinos desde un origen
        
        Args:
            lista_destinos (list): Lista de códigos postales destino
            cp_origen (str): Código postal origen (default: 40812)
        
        Returns:
            dict: Diccionario con resultados por destino
        """
        resultados = {}
        
        for cp_destino in lista_destinos:
            resultados[cp_destino] = self.calcular_distancia(cp_origen, cp_destino)
        
        return resultados
    
    def validar_codigo_postal(self, cp, pais='Mexico'):
        """
        Valida que un código postal exista
        
        Args:
            cp (str): Código postal a validar
            pais (str): País (default: Mexico)
        
        Returns:
            dict: Resultado de validación
        """
        try:
            url = 'https://maps.googleapis.com/maps/api/geocode/json'
            params = {
                'address': f'{cp},{pais}',
                'key': self.api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data['status'] == 'OK' and len(data['results']) > 0:
                return {
                    'success': True,
                    'direccion_formateada': data['results'][0]['formatted_address'],
                    'ubicacion': data['results'][0]['geometry']['location']
                }
            else:
                return {
                    'success': False,
                    'error': 'Código postal no encontrado'
                }
                
        except Exception as e:
            return {
                'success': False,
                'error': f"Error: {str(e)}"
            }