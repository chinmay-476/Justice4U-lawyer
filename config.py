import os
from dotenv import load_dotenv

load_dotenv()

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
