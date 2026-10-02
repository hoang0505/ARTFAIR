"""
ARTFAIR - WSGI Configuration Template for PythonAnywhere.
This file can be directly pasted into the PythonAnywhere WSGI configuration editor:
/var/www/<your-username>_pythonanywhere_com_wsgi.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ==============================================================================
# 1. PATH CONFIGURATION
# Thay đổi <your-username> thành username tài khoản PythonAnywhere của bạn
# Ví dụ: nếu username là 'nguyenvana', thì đường dẫn là /home/nguyenvana/ARTFAIR
# ==============================================================================
PA_USERNAME = os.environ.get('PA_USERNAME', '<your-username>')
PROJECT_HOME = f'/home/{PA_USERNAME}/ARTFAIR'
BACKEND_DIR = f'{PROJECT_HOME}/artfair_backend'

# Đưa backend và project root vào sys.path của Python
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if PROJECT_HOME not in sys.path:
    sys.path.insert(1, PROJECT_HOME)

# ==============================================================================
# 2. LOAD ENVIRONMENT VARIABLES (.env)
# ==============================================================================
env_path = os.path.join(BACKEND_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

# ==============================================================================
# 3. SET DJANGO SETTINGS MODULE
# ==============================================================================
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

# ==============================================================================
# 4. INITIALIZE DJANGO APPLICATION
# ==============================================================================
from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
