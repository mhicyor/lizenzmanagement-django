"""
WSGI config for lizenz_web project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

os.environ["DEMO_READ_ONLY"] = "1"

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lizenz_web.settings')

application = get_wsgi_application()
