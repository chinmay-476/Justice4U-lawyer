from flask import render_template, request, jsonify, redirect, url_for, flash, send_from_directory
import os
import json
import uuid
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from core import app, csrf, limiter, EMAIL_CONFIG, send_email, get_db_connection, is_admin_authenticated, get_current_lawyer_id, sanitize_input, validate_email, validate_phone, normalize_indian_phone, add_contact_message, add_lawyer_application, add_lawyer_application_fallback, get_lawyer_by_id, add_lawyer_to_db, add_rating, get_all_lawyers_from_db, get_lawyer_applications_fallback, create_lawyer_from_application, log_application_action, SEND_APPROVAL_EMAIL, SEND_REJECTION_EMAIL, UPLOAD_FOLDER

@app.route('/admin/login', methods=['GET', 'POST'])
@csrf.exempt
def admin_login():
    if request.method == 'GET':
        return render_template('admin_login.html', hide_chrome=True)
    password = (request.form.get('password') or '').strip()
    admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
    if password == admin_password:
        resp = redirect(url_for('admin_dashboard'))
        resp.set_cookie('is_admin', '1')
        return resp
    flash('Invalid admin password', 'error')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    resp = redirect(url_for('admin_login'))
    resp.delete_cookie('is_admin')
    return resp

@app.route('/portal/lawyer/login', methods=['GET', 'POST'])
@csrf.exempt
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
        # naive session using signed cookie
        resp = redirect(url_for('lawyer_dashboard'))
        resp.set_cookie('lawyer_id', str(lawyer['id']))
        resp.set_cookie('lawyer_name', lawyer['name'])
        return resp
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
def login_user():
    if request.method == 'GET':
        return render_template('login.html')
    email = sanitize_input(request.form.get('email', '')).lower()
    password = request.form.get('password', '')
    connection = get_db_connection()
    if not connection:
        flash('Database connection failed', 'error')
        return render_template('login.html')
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, email, password_hash FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        if not user or not check_password_hash(user['password_hash'], password):
            flash('Invalid credentials', 'error')
            return render_template('login.html')
        resp = redirect(url_for('user_home'))
        resp.set_cookie('user_id', str(user['id']))
        resp.set_cookie('user_name', user['name'])
        return resp
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/user/home')
def user_home():
    user_id = request.cookies.get('user_id')
    user_name = request.cookies.get('user_name')
    if not user_id:
        return redirect(url_for('login_user'))
    return render_template('user_home.html', user_name=user_name)

@app.route('/logout')
def logout_user():
    resp = redirect(url_for('home'))
    resp.delete_cookie('user_id')
    resp.delete_cookie('user_name')
    return resp

@app.route('/portal/lawyer/logout')
def lawyer_logout():
    resp = redirect(url_for('home'))
    resp.delete_cookie('lawyer_id')
    resp.delete_cookie('lawyer_name')
    return resp

