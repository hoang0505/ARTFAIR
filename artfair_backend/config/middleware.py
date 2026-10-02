"""
config/middleware.py
Middleware for ARTFAIR.
"""

from django.http import HttpResponseRedirect


class CanonicalFrontendRedirectMiddleware:
    """
    Ensures a single canonical website address for ARTFAIR.
    When users navigate to PythonAnywhere in a browser, this middleware
    seamlessly redirects non-API requests to the official GitHub Pages frontend:
    https://hoang0505.github.io/ARTFAIR/

    Infrastructure endpoints (/api/, /media/, /admin/) continue to be served directly.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info
        host = request.META.get('HTTP_HOST', '').lower()

        # Only redirect requests arriving at pythonanywhere domain
        if 'pythonanywhere.com' in host:
            # Preserve backend API, Media storage, and Django Admin
            if not (path.startswith('/api/') or path.startswith('/media/') or path.startswith('/admin/')):
                clean_path = path.lstrip('/')
                target_url = f"https://hoang0505.github.io/ARTFAIR/{clean_path}"
                if request.GET:
                    target_url += f"?{request.GET.urlencode()}"
                return HttpResponseRedirect(target_url)

        return self.get_response(request)
