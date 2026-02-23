from flask import Flask, request, jsonify, session
from flask_wtf import CSRFProtect
import mysql.connector
from mysql.connector import Error
import json
import re
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import html
import logging
from werkzeug.security import check_password_hash, generate_password_hash
from config import (
    DB_CONFIG,
    SECRET_KEY,
    EMAIL_CONFIG,
    UPLOAD_FOLDER,
    ALLOWED_EXTENSIONS,
    ENABLE_DEV_DOCS,
    MASTER_AUTH_EMAIL,
    MASTER_AUTH_PASSWORD,
)

load_dotenv()

applications_storage = []
application_counter = 0

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['WTF_CSRF_ENABLED'] = False
app.config['ENABLE_DEV_DOCS'] = ENABLE_DEV_DOCS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() in ('1', 'true', 'yes')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=int(os.getenv('SESSION_LIFETIME_HOURS', '8')))

csrf = CSRFProtect(app)
DISABLE_RATE_LIMITS = os.getenv('DISABLE_RATE_LIMITS', 'true').lower() in ('1', 'true', 'yes')

if DISABLE_RATE_LIMITS:
    class NoopLimiter:
        def limit(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator
    limiter = NoopLimiter()
else:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri=os.getenv('RATELIMIT_STORAGE_URL', 'memory://'))

os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.FileHandler('logs/app.log'), logging.StreamHandler()]
)

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.context_processor
def inject_user():
    user_name = session.get('user_name')
    return dict(user_name=user_name)

@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Content-Security-Policy', "default-src 'self' 'unsafe-inline' data: https:;")
    return response

def validate_email_config():
    missing = []
    if not EMAIL_CONFIG.get('smtp_server'):
        missing.append('SMTP_SERVER')
    if not EMAIL_CONFIG.get('smtp_port'):
        missing.append('SMTP_PORT')
    if not EMAIL_CONFIG.get('email'):
        missing.append('ADMIN_EMAIL')
    if not EMAIL_CONFIG.get('password'):
        missing.append('EMAIL_PASSWORD')
    if missing:
        logging.warning(f"Email config missing: {', '.join(missing)}. Emails will not be sent.")
        return False
    return True

@app.errorhandler(429)
def ratelimit_handler(e):
    logging.warning(f"Rate limit exceeded: {request.remote_addr}")
    return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429

@app.errorhandler(400)
def bad_request_handler(e):
    logging.warning(f"Bad request: {request.remote_addr} - {str(e)}")
    return jsonify({'error': 'Bad request. Please check your input.'}), 400

@app.errorhandler(500)
def internal_error_handler(e):
    logging.error(f"Internal server error: {str(e)}")
    return jsonify({'error': 'Internal server error. Please try again later.'}), 500

def sanitize_input(text):
    """Sanitize user input to prevent XSS attacks"""
    if not text:
        return ""
    # Remove HTML tags and escape special characters
    return html.escape(text.strip())

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_phone(phone):
    """Validate Indian mobile numbers: 10 digits starting 6-9, optional +91/0 prefix"""
    # Keep digits only for validation
    digits = re.sub(r'\D', '', phone or '')
    if not digits:
        return False
    # Strip country or trunk prefix
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith('0') and len(digits) == 11:
        digits = digits[1:]
    # Must be 10 digits, starting 6-9
    return len(digits) == 10 and digits[0] in '6789'

def sanitize_phone(phone):
    # Remove spaces, dashes, parentheses from phone number
    return re.sub(r'[\s\-\(\)]', '', phone or '')

def normalize_indian_phone(phone):
    """Normalize to E.164 +91XXXXXXXXXX for valid Indian mobile numbers"""
    digits = re.sub(r'\D', '', phone or '')
    if digits.startswith('91') and len(digits) == 12:
        local = digits[2:]
    elif digits.startswith('0') and len(digits) == 11:
        local = digits[1:]
    elif len(digits) == 10:
        local = digits
    else:
        return phone  # return original if cannot normalize
    if len(local) == 10 and local[0] in '6789':
        return f'+91{local}'
    return phone

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    """Create and return a database connection"""
    try:
        # Add a sane connection timeout
        connection = mysql.connector.connect(**DB_CONFIG, connection_timeout=5)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def send_email(to_email, subject, body):
    """Send email notification"""
    try:
        if not EMAIL_CONFIG_VALID:
            logging.warning('Email config invalid or incomplete; skipping send_email')
            return False

        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['email']
        msg['To'] = to_email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'html'))
        
        # Use STARTTLS with timeout; for port 465, switch to SMTP_SSL
        smtp_server = EMAIL_CONFIG['smtp_server']
        smtp_port = EMAIL_CONFIG['smtp_port']
        smtp_user = EMAIL_CONFIG['email']
        smtp_pass = EMAIL_CONFIG['password']

        if int(smtp_port) == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
            server.ehlo()
            server.starttls()
            server.ehlo()

        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_email], msg.as_string())
        server.quit()
        
        return True
    except Exception as e:
        logging.error(f"Error sending email: {type(e).__name__}: {e}")
        return False

def check_duplicate_lawyer(email, phone):
    """Check if lawyer with same email or phone already exists"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        # Reduce metadata lock wait for DDL
        try:
            cursor.execute("SET SESSION lock_wait_timeout = 3")
        except Exception:
            pass
        query = "SELECT id FROM lawyers WHERE email = %s OR phone = %s"
        cursor.execute(query, (email, phone))
        result = cursor.fetchone()
        return result is not None
        
    except Error as e:
        print(f"Error checking duplicate lawyer: {e}")
        return False
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def init_database():
    """Initialize the database with tables if they don't exist"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        
        # Create lawyers table (with UNIQUE email constraint)
        create_lawyers_table = """
        CREATE TABLE IF NOT EXISTS lawyers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            specialization VARCHAR(255) NOT NULL,
            years_experience INT NOT NULL,
            rating DECIMAL(2,1) DEFAULT 0.0,
            total_ratings INT DEFAULT 0,
            rating_sum INT DEFAULT 0,
            bio TEXT NOT NULL,
            qualification TEXT,
            biodata TEXT,
            case_win_rate DECIMAL(5,2) DEFAULT 0.0,
            total_cases INT DEFAULT 0,
            won_cases INT DEFAULT 0,
            photo VARCHAR(500) DEFAULT 'https://via.placeholder.com/300x300/3730a3/ffffff?text=Lawyer',
            phone VARCHAR(50) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            location VARCHAR(255) NOT NULL,
            state VARCHAR(100),
            district VARCHAR(100),
            pincode VARCHAR(10),
            court_workplace VARCHAR(255),
            consultation_fee DECIMAL(10,2),
            case_fee_range VARCHAR(50),
            keywords JSON,
            status ENUM('verified', 'pending', 'rejected') DEFAULT 'verified',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
        
        # Create users table for site users
        create_users_table = """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            phone VARCHAR(30),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        # Create user_cases table for tracking user legal matters
        create_user_cases_table = """
        CREATE TABLE IF NOT EXISTS user_cases (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            lawyer_id INT,
            case_title VARCHAR(255) NOT NULL,
            case_type VARCHAR(100) NOT NULL,
            case_description TEXT,
            case_status ENUM('open', 'in_progress', 'closed', 'pending') DEFAULT 'open',
            priority ENUM('low', 'medium', 'high', 'urgent') DEFAULT 'medium',
            budget_range VARCHAR(50),
            timeline VARCHAR(100),
            documents JSON,
            incident_date DATE,
            location VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (lawyer_id) REFERENCES lawyers(id) ON DELETE SET NULL,
            INDEX idx_user_cases_user_id (user_id),
            INDEX idx_user_cases_lawyer_id (lawyer_id),
            INDEX idx_user_cases_status (case_status),
            INDEX idx_user_cases_type (case_type)
        )
        """
        
        # Create lawyer applications table (enhanced with location and document fields)
        create_applications_table = """
        CREATE TABLE IF NOT EXISTS lawyer_applications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            phone VARCHAR(50) NOT NULL,
            license_number VARCHAR(100) NOT NULL,
            degree VARCHAR(255) NOT NULL,
            specialization VARCHAR(255) NOT NULL,
            years_experience INT NOT NULL,
            bio TEXT,
            location VARCHAR(255) NOT NULL,
            state VARCHAR(100),
            district VARCHAR(100),
            pincode VARCHAR(10),
            court_workplace VARCHAR(255),
            document_path VARCHAR(500),
            photo_path VARCHAR(500),
            consultation_fee DECIMAL(10,2),
            case_fee_range VARCHAR(50),
            verification_status ENUM('pending', 'verified', 'rejected') DEFAULT 'pending',
            status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
            rejection_reason TEXT,
            processed_by VARCHAR(255),
            processed_at TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
        
        # Create contact messages table
        create_contacts_table = """
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            message TEXT NOT NULL,
            phone VARCHAR(50),
            subject VARCHAR(100) DEFAULT 'general',
            legal_area VARCHAR(100),
            urgency ENUM('low', 'medium', 'high') DEFAULT 'low',
            status ENUM('new', 'read', 'replied') DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        # Create ratings table
        create_ratings_table = """
        CREATE TABLE IF NOT EXISTS lawyer_ratings (
            id INT AUTO_INCREMENT PRIMARY KEY,
            lawyer_id INT NOT NULL,
            user_ip VARCHAR(45) NOT NULL,
            rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lawyer_id) REFERENCES lawyers(id) ON DELETE CASCADE,
            UNIQUE KEY unique_user_lawyer (lawyer_id, user_ip)
        )
        """
        
        # Create application audit log table
        create_audit_table = """
        CREATE TABLE IF NOT EXISTS application_audit_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            application_id INT NOT NULL,
            action VARCHAR(50) NOT NULL,
            old_status VARCHAR(50),
            new_status VARCHAR(50),
            reason TEXT,
            processed_by VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (application_id) REFERENCES lawyer_applications(id) ON DELETE CASCADE
        )
        """
        
        # Messages from clients to lawyers
        create_lawyer_messages_table = """
        CREATE TABLE IF NOT EXISTS lawyer_client_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            lawyer_id INT NOT NULL,
            client_name VARCHAR(255) NOT NULL,
            client_email VARCHAR(255) NOT NULL,
            client_phone VARCHAR(30),
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lawyer_id) REFERENCES lawyers(id) ON DELETE CASCADE
        )
        """

        # Create email verification tokens table
        create_verification_tokens_table = """
        CREATE TABLE IF NOT EXISTS verification_tokens (
            id INT AUTO_INCREMENT PRIMARY KEY,
            lawyer_id INT NOT NULL,
            token VARCHAR(64) NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lawyer_id) REFERENCES lawyers(id) ON DELETE CASCADE
        )
        """

        create_master_auth_table = """
        CREATE TABLE IF NOT EXISTS master_auth (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            can_admin TINYINT(1) NOT NULL DEFAULT 0,
            can_user TINYINT(1) NOT NULL DEFAULT 0,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """

        create_login_audit_table = """
        CREATE TABLE IF NOT EXISTS login_audit (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            email_or_identity VARCHAR(255) NOT NULL,
            role_attempted VARCHAR(50) NOT NULL,
            status ENUM('success', 'failure') NOT NULL,
            source ENUM('master', 'regular') NOT NULL,
            ip_address VARCHAR(45),
            user_agent VARCHAR(512),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        
        cursor.execute(create_lawyers_table)
        cursor.execute(create_users_table)
        cursor.execute(create_user_cases_table)
        cursor.execute(create_applications_table)
        cursor.execute(create_contacts_table)
        cursor.execute(create_ratings_table)
        cursor.execute(create_audit_table)
        cursor.execute(create_lawyer_messages_table)
        cursor.execute(create_verification_tokens_table)
        cursor.execute(create_master_auth_table)
        cursor.execute(create_login_audit_table)
        
        # Create indexes (skip if they already exist)
        indexes = [
            "CREATE INDEX idx_lawyers_specialization ON lawyers(specialization)",
            "CREATE INDEX idx_lawyers_rating ON lawyers(rating)",
            "CREATE INDEX idx_lawyers_status ON lawyers(status)",
            "CREATE INDEX idx_lawyers_email ON lawyers(email)",
            "CREATE INDEX idx_applications_status ON lawyer_applications(status)",
            "CREATE INDEX idx_applications_email ON lawyer_applications(email)",
            "CREATE INDEX idx_contacts_status ON contact_messages(status)",
            "CREATE INDEX idx_lawyer_messages_lawyer_id ON lawyer_client_messages(lawyer_id)",
            "CREATE INDEX idx_verification_token ON verification_tokens(token)",
            "CREATE INDEX idx_login_audit_created_at ON login_audit(created_at)",
            "CREATE INDEX idx_login_audit_role_status ON login_audit(role_attempted, status)"
        ]
        
        for index_query in indexes:
            try:
                cursor.execute(index_query)
            except Error as e:
                # 1061: Duplicate key name (index already exists) – safe to ignore
                if getattr(e, 'errno', None) == 1061:
                    pass
                else:
                    raise
        
        connection.commit()
        ensure_master_auth_seed()
        return True
        
    except Error as e:
        print(f"Error creating tables: {e}")
        return False
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def get_all_lawyers_from_db(status='verified'):
    """Fetch all lawyers from database"""
    connection = get_db_connection()
    if not connection:
        return []
    
    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM lawyers WHERE status = %s ORDER BY rating DESC, years_experience DESC"
        cursor.execute(query, (status,))
        lawyers = cursor.fetchall()
        
        # Parse JSON keywords
        for lawyer in lawyers:
            if lawyer['keywords']:
                lawyer['keywords'] = json.loads(lawyer['keywords'])
            else:
                lawyer['keywords'] = []
        
        return lawyers
        
    except Error as e:
        print(f"Error fetching lawyers: {e}")
        return []
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def get_lawyer_by_id(lawyer_id):
    """Fetch a specific lawyer by ID"""
    connection = get_db_connection()
    if not connection:
        return None
    
    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM lawyers WHERE id = %s"
        cursor.execute(query, (lawyer_id,))
        lawyer = cursor.fetchone()
        
        if lawyer and lawyer['keywords']:
            lawyer['keywords'] = json.loads(lawyer['keywords'])
        elif lawyer:
            lawyer['keywords'] = []
        
        return lawyer
        
    except Error as e:
        print(f"Error fetching lawyer: {e}")
        return None
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def add_lawyer_to_db(lawyer_data):
    """Add a new lawyer to the database with duplicate checking"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        
        # Check for duplicates
        if check_duplicate_lawyer(lawyer_data['email'], lawyer_data['phone']):
            print(f"Duplicate lawyer found with email {lawyer_data['email']} or phone {lawyer_data['phone']}")
            return False
        
        keywords_json = json.dumps(lawyer_data['keywords'])
        
        query = """
        INSERT INTO lawyers (name, specialization, years_experience, rating, bio, qualification, biodata, case_win_rate, total_cases, won_cases, photo, phone, email, location, state, district, pincode, court_workplace, consultation_fee, case_fee_range, keywords, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        values = (
            lawyer_data['name'],
            lawyer_data['specialization'],
            lawyer_data['years_experience'],
            lawyer_data['rating'],
            lawyer_data['bio'],
            lawyer_data.get('qualification', ''),
            lawyer_data.get('biodata', ''),
            lawyer_data.get('case_win_rate', 0.0),
            lawyer_data.get('total_cases', 0),
            lawyer_data.get('won_cases', 0),
            lawyer_data['photo'],
            lawyer_data['phone'],
            lawyer_data['email'],
            lawyer_data['location'],
            lawyer_data.get('state'),
            lawyer_data.get('district'),
            lawyer_data.get('pincode'),
            lawyer_data.get('court_workplace'),
            lawyer_data.get('consultation_fee'),
            lawyer_data.get('case_fee_range'),
            keywords_json,
            lawyer_data.get('status', 'verified')
        )
        
        cursor.execute(query, values)
        connection.commit()
        return cursor.lastrowid
        
    except Error as e:
        print(f"Error adding lawyer: {e}")
        return False
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def add_lawyer_application(application_data):
    """Add a new lawyer application with document handling"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        
        # Check for duplicate applications
        check_query = "SELECT id FROM lawyer_applications WHERE email = %s AND status = 'pending'"
        cursor.execute(check_query, (application_data['email'],))
        if cursor.fetchone():
            print(f"Pending application already exists for email {application_data['email']}")
            return False
        
        query = """
        INSERT INTO lawyer_applications (name, email, phone, license_number, degree, specialization, years_experience, bio, location, state, district, pincode, court_workplace, document_path, photo_path, consultation_fee, case_fee_range)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        values = (
            application_data['name'],
            application_data['email'], 
            application_data['phone'],
            application_data['license_number'],
            application_data['degree'],
            application_data['specialization'],
            application_data['years_experience'],
            application_data['bio'],
            application_data.get('location', 'Not specified'),
            application_data.get('state', None),
            application_data.get('district', None),
            application_data.get('pincode', None),
            application_data.get('court_workplace', None),
            application_data.get('document_path', None),
            application_data.get('photo_path', None),
            application_data.get('consultation_fee', None),
            application_data.get('case_fee_range', None)
        )
        
        cursor.execute(query, values)
        connection.commit()
        return cursor.lastrowid
        
    except Error as e:
        print(f"Error adding lawyer application: {e}")
        return False
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def add_lawyer_application_fallback(application_data):
    """Add a new lawyer application to in-memory storage when database is not available"""
    global application_counter
    application_counter += 1
    
    application = {
        'id': application_counter,
        'name': application_data['name'],
        'email': application_data['email'],
        'phone': application_data['phone'],
        'license_number': application_data['license_number'],
        'degree': application_data['degree'],
        'specialization': application_data['specialization'],
        'years_experience': application_data['years_experience'],
        'bio': application_data['bio'],
        'location': application_data.get('location', 'Not specified'),
        'document_path': application_data.get('document_path', None),
        'status': 'pending',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    applications_storage.append(application)
    return application_counter

def get_lawyer_applications_fallback():
    """Get all lawyer applications from in-memory storage"""
    return applications_storage

def add_contact_message(contact_data):
    """Add a contact message with enhanced data structure"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        query = """
        INSERT INTO contact_messages (name, email, message, phone, subject, legal_area, urgency, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            contact_data['name'], 
            contact_data['email'], 
            contact_data['message'],
            normalize_indian_phone(contact_data.get('phone', None)) if contact_data.get('phone') else None,
            contact_data.get('subject', 'general'),
            contact_data.get('legal_area', None),
            contact_data.get('urgency', 'low'),
            'new'
        )
        cursor.execute(query, values)
        connection.commit()
        return cursor.lastrowid
        
    except Error as e:
        print(f"Error adding contact message: {e}")
        return False
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def add_rating(lawyer_id, rating, user_ip):
    """Add or update a rating for a lawyer"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        
        # Check if user already rated this lawyer
        check_query = "SELECT rating FROM lawyer_ratings WHERE lawyer_id = %s AND user_ip = %s"
        cursor.execute(check_query, (lawyer_id, user_ip))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing rating
            old_rating = existing[0]
            update_query = "UPDATE lawyer_ratings SET rating = %s WHERE lawyer_id = %s AND user_ip = %s"
            cursor.execute(update_query, (rating, lawyer_id, user_ip))
            
            # Update lawyer's rating statistics
            update_lawyer_query = """
            UPDATE lawyers 
            SET rating_sum = rating_sum - %s + %s, 
                rating = ROUND((rating_sum - %s + %s) / total_ratings, 2)
            WHERE id = %s
            """
            cursor.execute(update_lawyer_query, (old_rating, rating, old_rating, rating, lawyer_id))
        else:
            # Insert new rating
            insert_query = "INSERT INTO lawyer_ratings (lawyer_id, user_ip, rating) VALUES (%s, %s, %s)"
            cursor.execute(insert_query, (lawyer_id, user_ip, rating))
            
            # Update lawyer's rating statistics
            update_lawyer_query = """
            UPDATE lawyers 
            SET total_ratings = total_ratings + 1,
                rating_sum = rating_sum + %s,
                rating = ROUND((rating_sum + %s) / (total_ratings + 1), 2)
            WHERE id = %s
            """
            cursor.execute(update_lawyer_query, (rating, rating, lawyer_id))
        
        connection.commit()
        return True
        
    except Error as e:
        print(f"Error adding/updating rating: {e}")
        return False
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def log_application_action(application_id, action, old_status, new_status, reason=None, processed_by="Admin"):
    """Log application processing actions"""
    connection = get_db_connection()
    if not connection:
        return False
    
    try:
        cursor = connection.cursor()
        query = """
        INSERT INTO application_audit_log (application_id, action, old_status, new_status, reason, processed_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (application_id, action, old_status, new_status, reason, processed_by))
        connection.commit()
        return True
        
    except Error as e:
        print(f"Error logging application action: {e}")
        return False
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

def create_lawyer_from_application(application):
    """Create a lawyer profile from approved application"""
    try:
        # Generate keywords from specialization and other fields
        keywords = [
            application['specialization'].lower(),
            'lawyer',
            'legal',
            'attorney'
        ]
        
        # Add experience level keywords
        if application['years_experience'] >= 10:
            keywords.append('experienced')
        elif application['years_experience'] >= 5:
            keywords.append('skilled')
        else:
            keywords.append('qualified')
        
        # Create default bio if none provided
        bio = application['bio'] or f"""Experienced {application['specialization']} attorney with {application['years_experience']} years of dedicated legal practice. 
        
Licensed professional committed to providing exceptional legal services. Graduate with {application['degree']} qualification.
Contact me for professional legal consultation and representation."""
        
        # Use uploaded photo if available, otherwise use default
        photo_url = 'https://via.placeholder.com/300x300/3730a3/ffffff?text=Lawyer'
        if application.get('photo_path'):
            # Convert file path to URL for web access
            photo_filename = os.path.basename(application['photo_path'])
            photo_url = f"/uploads/{photo_filename}"
        
        lawyer_data = {
            'name': application['name'].strip(),
            'specialization': application['specialization'].strip(),
            'years_experience': application['years_experience'],
            'rating': 0.0,
            'bio': bio,
            'qualification': application.get('degree', ''),
            'biodata': f"Professional lawyer with {application['years_experience']} years of experience in {application['specialization']}. Licensed professional committed to providing quality legal services.",
            'case_win_rate': 0.0,
            'total_cases': 0,
            'won_cases': 0,
            'photo': photo_url,
            'phone': application['phone'].strip(),
            'email': application['email'].strip().lower(),
            'location': application.get('location', 'Not specified').strip(),
            'state': application.get('state'),
            'district': application.get('district'),
            'pincode': application.get('pincode'),
            'court_workplace': application.get('court_workplace'),
            'consultation_fee': application.get('consultation_fee'),
            'case_fee_range': application.get('case_fee_range'),
            'keywords': keywords,
            'status': 'verified'
        }
        
        return add_lawyer_to_db(lawyer_data)
        
    except Exception as e:
        print(f"Error creating lawyer from application: {e}")
        return False


def ensure_master_auth_seed():
    """Ensure master auth credentials exist and stay role-enabled."""
    connection = get_db_connection()
    if not connection:
        return False

    cursor = None
    try:
        cursor = connection.cursor()
        password_hash = generate_password_hash(MASTER_AUTH_PASSWORD)
        cursor.execute(
            """
            INSERT INTO master_auth (email, password_hash, can_admin, can_user, is_active)
            VALUES (%s, %s, 1, 1, 1)
            ON DUPLICATE KEY UPDATE
                password_hash = VALUES(password_hash),
                can_admin = VALUES(can_admin),
                can_user = VALUES(can_user),
                is_active = VALUES(is_active),
                updated_at = CURRENT_TIMESTAMP
            """,
            (MASTER_AUTH_EMAIL, password_hash),
        )
        connection.commit()
        return True
    except Error as e:
        logging.error(f"Error seeding master_auth: {e}")
        return False
    finally:
        try:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
        except Exception:
            pass


def verify_master_credentials(email, password, role):
    """Check master credentials and role permission."""
    normalized_email = (email or "").strip().lower()
    if not normalized_email or not password:
        return False

    connection = get_db_connection()
    if not connection:
        return False

    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT email, password_hash, can_admin, can_user, is_active
            FROM master_auth
            WHERE email = %s
            LIMIT 1
            """,
            (normalized_email,),
        )
        row = cursor.fetchone()
        if not row or not bool(row.get("is_active")):
            return False
        if role == "admin" and not bool(row.get("can_admin")):
            return False
        if role == "user" and not bool(row.get("can_user")):
            return False
        return check_password_hash(row["password_hash"], password)
    except Error:
        return False
    finally:
        try:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
        except Exception:
            pass


def log_login_audit(email_or_identity, role_attempted, status, source, ip_address=None, user_agent=None):
    """Persist login outcomes for traceability and anomaly review."""
    connection = get_db_connection()
    if not connection:
        return False

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO login_audit (email_or_identity, role_attempted, status, source, ip_address, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                (email_or_identity or "unknown")[:255],
                (role_attempted or "unknown")[:50],
                "success" if status == "success" else "failure",
                "master" if source == "master" else "regular",
                (ip_address or "")[:45] or None,
                (user_agent or "")[:512] or None,
            ),
        )
        connection.commit()
        return True
    except Error:
        return False
    finally:
        try:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
        except Exception:
            pass


def get_login_audit_entries(page=1, per_page=25, sort="desc"):
    """Return paginated login audit rows for admin monitoring UI/API."""
    connection = get_db_connection()
    if not connection:
        return {"items": [], "total": 0, "page": 1, "per_page": per_page, "sort": sort}

    safe_page = max(int(page or 1), 1)
    safe_per_page = min(max(int(per_page or 25), 1), 100)
    safe_sort = "asc" if str(sort).lower() == "asc" else "desc"
    order_sql = "ASC" if safe_sort == "asc" else "DESC"
    offset = (safe_page - 1) * safe_per_page

    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS total FROM login_audit")
        total = int((cursor.fetchone() or {}).get("total", 0))
        cursor.execute(
            f"""
            SELECT id, email_or_identity, role_attempted, status, source, ip_address, user_agent, created_at
            FROM login_audit
            ORDER BY created_at {order_sql}, id {order_sql}
            LIMIT %s OFFSET %s
            """,
            (safe_per_page, offset),
        )
        items = cursor.fetchall() or []
        return {
            "items": items,
            "total": total,
            "page": safe_page,
            "per_page": safe_per_page,
            "sort": safe_sort,
        }
    except Error:
        return {"items": [], "total": 0, "page": safe_page, "per_page": safe_per_page, "sort": safe_sort}
    finally:
        try:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
        except Exception:
            pass

def is_admin_authenticated():
    return bool(session.get('is_admin'))

def get_current_lawyer_id():
    lawyer_id = session.get('lawyer_id')
    try:
        return int(lawyer_id) if lawyer_id else None
    except Exception:
        return None

EMAIL_CONFIG_VALID = validate_email_config()
SEND_APPROVAL_EMAIL = os.getenv('SEND_APPROVAL_EMAIL', 'false').lower() in ('1','true','yes')
SEND_REJECTION_EMAIL = os.getenv('SEND_REJECTION_EMAIL', 'false').lower() in ('1','true','yes')
