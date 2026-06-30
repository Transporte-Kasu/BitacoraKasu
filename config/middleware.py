import threading

_thread_locals = threading.local()


def get_current_user():
    return getattr(_thread_locals, 'user', None)


def get_current_ip():
    return getattr(_thread_locals, 'ip', None)


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.user = getattr(request, 'user', None)
        _thread_locals.ip = self._get_ip(request)
        return self.get_response(request)

    @staticmethod
    def _get_ip(request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
