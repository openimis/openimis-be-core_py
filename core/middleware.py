from django.utils.timezone import now


class DefaultAxesAttributesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Set default values for Django-axes attributes if they're not already set
        if not hasattr(request, 'axes_ip_address'):
            request.axes_ip_address = request.META.get('REMOTE_ADDR', '')
        if not hasattr(request, 'axes_user_agent'):
            request.axes_user_agent = request.META.get('HTTP_USER_AGENT', '')
        if not hasattr(request, 'axes_attempt_time'):
            request.axes_attempt_time = now()

        return self.get_response(request)
