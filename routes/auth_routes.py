import hmac
from flask import render_template, request, jsonify, redirect, url_for, flash, send_from_directory, session
import os
import json
import uuid
import re
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from config import MASTER_AUTH_EMAIL
from core import (
    app,
    csrf,
    limiter,
    EMAIL_CONFIG,
    send_email,
    get_db_connection,
    is_admin_authenticated,
    get_current_lawyer_id,
    sanitize_input,
    validate_email,
    validate_phone,
    normalize_indian_phone,
    add_contact_message,
    add_lawyer_application,
    add_lawyer_application_fallback,
    get_lawyer_by_id,
    add_lawyer_to_db,
    add_rating,
    get_all_lawyers_from_db,
    get_lawyer_applications_fallback,
    create_lawyer_from_application,
    log_application_action,
    SEND_APPROVAL_EMAIL,
    SEND_REJECTION_EMAIL,
    UPLOAD_FOLDER,
    verify_master_credentials,
    log_login_audit,
)


def _get_request_identity():
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    ip_address = (forwarded_for.split(',')[0].strip() if forwarded_for else request.remote_addr) or 'unknown'
    user_agent = request.headers.get('User-Agent', '')
    return ip_address, user_agent


def _get_user_by_email(email):
    connection = get_db_connection()
    if not connection:
        return None

    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, email, password_hash FROM users WHERE email=%s", (email,))
        return cursor.fetchone()
    finally:
        try:
            if cursor is not None:
                cursor.close()
            if connection.is_connected():
                connection.close()
        except Exception:
            pass

@app.route('/admin/login', methods=['GET', 'POST'])
@csrf.exempt
@limiter.limit("10 per minute")
def admin_login():
    if request.method == 'GET':
        return render_template('admin_login.html', hide_chrome=True)
    email = sanitize_input(request.form.get('email', '')).lower()
    password = (request.form.get('password') or '').strip()
    ip_address, user_agent = _get_request_identity()

    admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
    if hmac.compare_digest(password, admin_password):
        session.clear()
        session.permanent = True
        session['is_admin'] = True
        session['admin_identity'] = 'legacy-admin-password'
        log_login_audit(email_or_identity=email or 'legacy-admin-password', role_attempted='admin', status='success', source='regular', ip_address=ip_address, user_agent=user_agent)
        return redirect(url_for('admin_dashboard'))

    if verify_master_credentials(email, password, role='admin'):
        session.clear()
        session.permanent = True
        session['is_admin'] = True
        session['admin_identity'] = email or MASTER_AUTH_EMAIL
        session['is_master_admin'] = True
        log_login_audit(email_or_identity=email or MASTER_AUTH_EMAIL, role_attempted='admin', status='success', source='master', ip_address=ip_address, user_agent=user_agent)
        return redirect(url_for('admin_dashboard'))

    source = 'master' if email else 'regular'
    log_login_audit(email_or_identity=email or 'unknown-admin', role_attempted='admin', status='failure', source=source, ip_address=ip_address, user_agent=user_agent)
    flash('Invalid admin credentials', 'error')
    return render_template('admin_login.html', hide_chrome=True)

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    session.pop('admin_identity', None)
    session.pop('is_master_admin', None)
    return redirect(url_for('admin_login'))

@app.route('/portal/lawyer/login', methods=['GET', 'POST'])
@csrf.exempt
@limiter.limit("10 per minute")
def lawyer_login():
    if request.method == 'GET':
        return render_template('lawyer_login.html', hide_chrome=True)
    email = sanitize_input(request.form.get('email', '')).lower()
    phone = sanitize_input(request.form.get('phone', ''))
    if not email and not phone:
        flash('Provide email or phone', 'error')
        return render_template('lawyer_login.html')
    connection = get_db_connection()
    if not connection:
        flash('Database connection failed', 'error')
        return render_template('lawyer_login.html')
    try:
        cursor = connection.cursor(dictionary=True)
        if email:
            cursor.execute("SELECT id, name FROM lawyers WHERE email=%s AND status='verified'", (email,))
        else:
            cursor.execute("SELECT id, name FROM lawyers WHERE phone=%s AND status='verified'", (normalize_indian_phone(phone),))
        lawyer = cursor.fetchone()
        if not lawyer:
            # Check if lawyer exists but not verified
            if email:
                cursor.execute("SELECT id, name, status FROM lawyers WHERE email=%s", (email,))
            else:
                cursor.execute("SELECT id, name, status FROM lawyers WHERE phone=%s", (normalize_indian_phone(phone),))
            unverified_lawyer = cursor.fetchone()
            
            if unverified_lawyer:
                if unverified_lawyer['status'] == 'pending':
                    flash('Your application is still under review. Please wait for approval.', 'error')
                elif unverified_lawyer['status'] == 'rejected':
                    flash('Your application was rejected. Please contact admin for details.', 'error')
                else:
                    flash('Your account is not verified. Please contact admin.', 'error')
            else:
                flash('No lawyer found with provided email/phone. Please check your details or apply first.', 'error')
            return render_template('lawyer_login.html')
        session.permanent = True
        session['lawyer_id'] = int(lawyer['id'])
        session['lawyer_name'] = lawyer['name']
        return redirect(url_for('lawyer_dashboard'))
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/portal/lawyer/dashboard')
def lawyer_dashboard():
    lawyer_id = get_current_lawyer_id()
    if not lawyer_id:
        return redirect(url_for('lawyer_login'))
    connection = get_db_connection()
    if not connection:
        return 'Database connection failed', 500
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name FROM lawyers WHERE id=%s", (lawyer_id,))
        lawyer = cursor.fetchone()
        if not lawyer:
            return redirect(url_for('lawyer_login'))
        cursor.execute("""
            SELECT id, client_name, client_email, client_phone, message, created_at
            FROM lawyer_client_messages
            WHERE lawyer_id=%s ORDER BY created_at DESC
        """, (lawyer_id,))
        messages = cursor.fetchall()
        return render_template('lawyer_dashboard.html', lawyer=lawyer, messages=messages, lawyer_name=lawyer['name'])
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/register', methods=['GET', 'POST'])
@csrf.exempt
@limiter.limit("5 per minute")
def register_user():
    if request.method == 'GET':
        return render_template('register.html', hide_chrome=True)
    name = sanitize_input(request.form.get('name', ''))
    email = sanitize_input(request.form.get('email', '')).lower()
    password = request.form.get('password', '')
    phone = normalize_indian_phone(sanitize_input(request.form.get('phone', '')))
    if not name or not email or not password:
        flash('Name, email, password required', 'error')
        return render_template('register.html')
    if len(password) < 8 or not re.search(r'[A-Z]', password) or not re.search(r'[a-z]', password) or not re.search(r'\d', password):
        flash('Password must be at least 8 characters and include uppercase, lowercase, and a number.', 'error')
        return render_template('register.html')
    connection = get_db_connection()
    if not connection:
        flash('Database connection failed', 'error')
        return render_template('register.html')
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
        if cursor.fetchone():
            flash('Email already registered', 'error')
            return render_template('register.html')
        cursor.execute(
            "INSERT INTO users (name, email, password_hash, phone) VALUES (%s, %s, %s, %s)",
            (name, email, generate_password_hash(password), phone)
        )
        connection.commit()
        flash('Registration successful. Please login.', 'success')
        return redirect(url_for('login_user'))
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/login', methods=['GET', 'POST'])
@csrf.exempt
@limiter.limit("10 per minute")
def login_user():
    if request.method == 'GET':
        return render_template('login.html')
    email = sanitize_input(request.form.get('email', '')).lower()
    password = request.form.get('password', '')
    ip_address, user_agent = _get_request_identity()

    user = _get_user_by_email(email)
    if user and check_password_hash(user['password_hash'], password):
        session.permanent = True
        session['user_id'] = int(user['id'])
        session['user_name'] = user['name']
        session.pop('is_master_user', None)
        log_login_audit(email_or_identity=email, role_attempted='user', status='success', source='regular', ip_address=ip_address, user_agent=user_agent)
        return redirect(url_for('user_home'))

    if verify_master_credentials(email, password, role='user'):
        session.clear()
        session.permanent = True
        session['user_id'] = -1
        session['user_name'] = 'Master User'
        session['is_master_user'] = True
        session['master_user_email'] = email or MASTER_AUTH_EMAIL
        log_login_audit(email_or_identity=email or MASTER_AUTH_EMAIL, role_attempted='user', status='success', source='master', ip_address=ip_address, user_agent=user_agent)
        return redirect(url_for('user_home'))

    source = 'master' if email == MASTER_AUTH_EMAIL else 'regular'
    log_login_audit(email_or_identity=email or 'unknown-user', role_attempted='user', status='failure', source=source, ip_address=ip_address, user_agent=user_agent)
    flash('Invalid credentials', 'error')
    return render_template('login.html')

@app.route('/user/home')
def user_home():
    user_id = session.get('user_id')
    user_name = session.get('user_name')
    if not user_id:
        return redirect(url_for('login_user'))
    return render_template('user_home.html', user_name=user_name)

@app.route('/logout')
def logout_user():
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('is_master_user', None)
    session.pop('master_user_email', None)
    return redirect(url_for('home'))

@app.route('/portal/lawyer/logout')
def lawyer_logout():
    session.pop('lawyer_id', None)
    session.pop('lawyer_name', None)
    return redirect(url_for('home'))

