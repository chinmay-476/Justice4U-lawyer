import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")

# Database Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'legalmatch_db'),
    'port': int(os.getenv('DB_PORT', 3306))
}

# Secret Key
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')

# Developer Docs Configuration
APP_ENV = os.getenv('FLASK_ENV', os.getenv('ENV', 'development')).strip().lower()
ENABLE_DEV_DOCS = _env_bool('ENABLE_DEV_DOCS', default=(APP_ENV != 'production'))

# Master Auth Configuration
MASTER_AUTH_EMAIL = os.getenv('MASTER_AUTH_EMAIL', 'chinmaysahoo63715@gmail.com').strip().lower()
MASTER_AUTH_PASSWORD = os.getenv('MASTER_AUTH_PASSWORD', 'chin1987')

# Email Configuration
EMAIL_CONFIG = {
    'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
    'smtp_port': int(os.getenv('SMTP_PORT', 587)),
    'email': os.getenv('ADMIN_EMAIL', ''),
    'password': os.getenv('EMAIL_PASSWORD', '')
}

# File Upload Configuration
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'doc', 'docx'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB
