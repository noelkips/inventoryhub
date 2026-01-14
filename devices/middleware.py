from django.contrib.auth import logout
from django.shortcuts import redirect
from django.utils import timezone
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class SessionTimeoutMiddleware:
    """
    Adds cache-control headers + optional very long inactivity warning.
    Actual timeout is now handled by Django session framework + frontend timer.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response = self.add_cache_control_headers(response, request)
        return response

    def add_cache_control_headers(self, response, request):
        content_type = response.get('Content-Type', '')

        # Skip for static, media, js, css, images...
        if any([
            '/static/' in request.path,
            '/media/' in request.path,
            'text/css' in content_type,
            'javascript' in content_type,
            'image/' in content_type,
            'font/' in content_type,
        ]):
            return response

        # Aggressive no-cache for HTML views
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate, private, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'

        if 'text/html' in content_type or not content_type:
            response['X-Content-Type-Options'] = 'nosniff'

        return response