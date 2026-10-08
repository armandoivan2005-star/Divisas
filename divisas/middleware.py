import logging
import time


class SecurityEventMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger('divisas.security')

    def __call__(self, request):
        started_at = time.perf_counter()
        response = self.get_response(request)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)

        username = request.user.username if request.user.is_authenticated else 'anon'
        client_ip = self.get_client_ip(request)
        status_code = response.status_code

        log_message = (
            f'access user={username} ip={client_ip} method={request.method} '
            f'path={request.path} status={status_code} latency_ms={elapsed_ms}'
        )

        if status_code >= 500:
            self.logger.error(log_message)
        elif status_code >= 400:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)

        return response

    @staticmethod
    def get_client_ip(request):
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')
