from django.http import JsonResponse
from .utils.ExceptionHandlerRegistry import ExceptionHandlerRegistry


class ExceptionHandlerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except Exception as e:
            handler_func = ExceptionHandlerRegistry.get_exception_handler(__name__)
            if handler_func:
                response_message = handler_func(e)
                response = JsonResponse({"error": response_message})
            else:
                response = JsonResponse({"error": str(e)})
        return response
