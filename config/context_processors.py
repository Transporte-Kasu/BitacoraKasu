def alertas_combustible(request):
    """Inyecta el conteo de alertas de combustible pendientes para superusuarios"""
    if request.user.is_authenticated and request.user.is_superuser:
        from modulos.combustible.models import AlertaCombustible
        count = AlertaCombustible.objects.filter(resuelta=False).count()
        return {'alertas_combustible_pendientes': count}
    return {'alertas_combustible_pendientes': 0}
