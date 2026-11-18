"""Content Security Policy.

Django 5.2 has no built-in CSP (6.0 adds one), and the app needs no inline
script or style, so a single strict, static policy covers every page,
including the admin. If an XSS bug ever slips into a template, the browser
still refuses to run injected scripts or load anything from another origin.
"""

from django.conf import settings


def _policy(directives: dict[str, str]) -> str:
    return "; ".join(f"{name} {value}" for name, value in directives.items())


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.header = (
            "Content-Security-Policy-Report-Only" if settings.CSP_REPORT_ONLY else "Content-Security-Policy"
        )
        self.policy = _policy(settings.CSP_DIRECTIVES)

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault(self.header, self.policy)
        return response
