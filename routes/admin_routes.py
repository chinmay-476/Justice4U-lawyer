from flask import abort, render_template, request, jsonify, redirect, url_for, flash, send_from_directory
import os
import json
import uuid
from datetime import datetime
from mysql.connector import Error
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from core import app, csrf, limiter, EMAIL_CONFIG, send_email, get_db_connection, is_admin_authenticated, get_current_lawyer_id, sanitize_input, validate_email, validate_phone, normalize_indian_phone, check_duplicate_lawyer, add_contact_message, add_lawyer_application, add_lawyer_application_fallback, get_lawyer_by_id, add_lawyer_to_db, add_rating, get_all_lawyers_from_db, get_lawyer_applications_fallback, create_lawyer_from_application, log_application_action, get_login_audit_entries, SEND_APPROVAL_EMAIL, SEND_REJECTION_EMAIL, UPLOAD_FOLDER

def _require_admin_api():
    if not is_admin_authenticated():
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    return None


def _guess_auth_requirement(path):
    if path in ('/admin/login', '/admin/logout'):
        return 'Public (admin auth entry)'
    if path.startswith('/admin') or path.startswith('/api/admin'):
        return 'Admin session'
    if path.startswith('/api/contact-messages') or path.startswith('/api/lawyer-applications'):
        return 'Admin session'
    if path.startswith('/api/applications') or path.startswith('/api/messages'):
        return 'Admin session'
    if path.startswith('/api/lawyers/') and (path.endswith('/status') or path.count('/') >= 3):
        return 'Mixed (public read + admin update/delete)'
    if path.startswith('/portal/lawyer/dashboard') or path.startswith('/portal/lawyer/logout'):
        return 'Lawyer session'
    if path.startswith('/user/home') or path == '/logout':
        return 'User session'
    return 'Public'


def _collect_api_inventory():
    inventory = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda item: item.rule):
        methods = sorted(method for method in rule.methods if method not in {'HEAD', 'OPTIONS'})
        if not methods:
            continue
        inventory.append(
            {
                'path': rule.rule,
                'methods': ', '.join(methods),
                'auth': _guess_auth_requirement(rule.rule),
                'endpoint': rule.endpoint,
            }
        )
    return inventory


def _fallback_schema_snapshot():
    return {
        'lawyers': ['id', 'name', 'email', 'phone', 'specialization', 'status', 'rating', 'created_at'],
        'users': ['id', 'name', 'email', 'password_hash', 'phone', 'created_at'],
        'user_cases': ['id', 'user_id', 'lawyer_id', 'case_title', 'case_type', 'case_status', 'documents'],
        'lawyer_applications': ['id', 'name', 'email', 'phone', 'specialization', 'status', 'processed_at'],
        'contact_messages': ['id', 'name', 'email', 'message', 'subject', 'status', 'created_at'],
        'lawyer_ratings': ['id', 'lawyer_id', 'user_ip', 'rating', 'created_at'],
        'application_audit_log': ['id', 'application_id', 'action', 'old_status', 'new_status', 'created_at'],
        'lawyer_client_messages': ['id', 'lawyer_id', 'client_name', 'client_email', 'message', 'created_at'],
        'verification_tokens': ['id', 'lawyer_id', 'token', 'expires_at', 'created_at'],
        'master_auth': ['id', 'email', 'password_hash', 'can_admin', 'can_user', 'is_active', 'created_at', 'updated_at'],
        'login_audit': ['id', 'email_or_identity', 'role_attempted', 'status', 'source', 'ip_address', 'user_agent', 'created_at'],
    }


def _collect_db_schema():
    connection = get_db_connection()
    if not connection:
        return _fallback_schema_snapshot(), 'fallback'

    schema = {}
    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute('SHOW TABLES')
        tables = [row[0] for row in cursor.fetchall()]
        for table_name in tables:
            cursor.execute(f"DESCRIBE `{table_name}`")
            columns = cursor.fetchall()
            schema[table_name] = [column[0] for column in columns]
    except Exception:
        schema = _fallback_schema_snapshot()
        return schema, 'fallback'
    finally:
        try:
            if cursor is not None:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()
        except Exception:
            pass

    return schema, 'mysql'


def _collect_frontend_assets():
    template_dir = os.path.join(app.root_path, 'templates')
    static_dir = os.path.join(app.root_path, 'static')
    templates = sorted([name for name in os.listdir(template_dir) if name.endswith('.html')]) if os.path.isdir(template_dir) else []
    static_items = sorted(os.listdir(static_dir)) if os.path.isdir(static_dir) else []
    return templates, static_items

@app.route('/api/admin/test-email', methods=['POST'])
@csrf.exempt
def test_email_endpoint():
    """Send a test email to verify SMTP settings (guarded by admin password)."""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    password = request.args.get('password') or (request.json or {}).get('password')
    to_email = request.args.get('to') or (request.json or {}).get('to') or EMAIL_CONFIG.get('email')
    admin_test_password = os.getenv('ADMIN_TEST_EMAIL_PASSWORD', '123')
    if password != admin_test_password:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    if not to_email:
        return jsonify({'success': False, 'error': 'Missing recipient email'}), 400
    subject = 'LegalMatch SMTP Test'
    body = '<html><body><h3>SMTP test successful.</h3><p>This is a test email.</p></body></html>'
    sent = send_email(to_email, subject, body)
    return jsonify({'success': bool(sent)}) if sent else (jsonify({'success': False, 'error': 'Failed to send email'}), 500)

@app.route('/admin')
def admin_dashboard():
    if not is_admin_authenticated():
        return redirect(url_for('admin_login'))
    return render_template('admin_dashboard.html')


@app.route('/admin/api/login-audit')
def admin_login_audit_api():
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error

    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=25, type=int)
    sort = (request.args.get('sort') or 'desc').strip().lower()
    payload = get_login_audit_entries(page=page, per_page=per_page, sort=sort)
    return jsonify({'success': True, **payload})


@app.route('/admin/dev-guide')
def admin_dev_guide():
    if not is_admin_authenticated():
        return redirect(url_for('admin_login'))
    if not app.config.get('ENABLE_DEV_DOCS', False):
        abort(404)

    api_inventory = _collect_api_inventory()
    db_schema, schema_source = _collect_db_schema()
    templates, static_items = _collect_frontend_assets()

    backend_modules = [
        {'file': 'app.py', 'purpose': 'Entrypoint and startup bootstrap'},
        {'file': 'core.py', 'purpose': 'Flask app, DB helpers, security headers, schema + master auth seed'},
        {'file': 'routes/public_routes.py', 'purpose': 'Public pages and client-facing APIs'},
        {'file': 'routes/auth_routes.py', 'purpose': 'Admin/lawyer/user auth flows incl. master auth fallback'},
        {'file': 'routes/admin_routes.py', 'purpose': 'Admin dashboard APIs, login audit API, and dev docs'},
        {'file': 'tests/test_routes_smoke.py', 'purpose': 'Route smoke regression checks'},
    ]

    realtime_notes = [
        'No WebSocket or Socket.IO server is currently implemented in the Lawyer project.',
        'Current interactions are request/response HTTP APIs with server-side session auth.',
        'Realtime notifications can be added later with Socket.IO or SSE after auth hardening.',
    ]

    runbook = [
        'pip install -r requirements.txt',
        'python app.py',
        'set PYTHONPATH=. && python tests/test_routes_smoke.py',
        'set PYTHONPATH=. && python -m unittest tests/test_auth_master_and_dev_docs.py',
    ]

    known_risks = [
        'Legacy ADMIN_PASSWORD path remains enabled for backward compatibility; migrate to MFA-backed admin identity.',
        'Some JSON mutation endpoints are csrf.exempt; these should be reviewed and reduced.',
        'Rate limits can be disabled by environment and should be enforced in production.',
        'Master auth credentials should be rotated through env vars before production deployment.',
    ]

    backlog = [
        {
            'priority': 'P0',
            'title': 'Security and reliability hardening',
            'items': [
                'Stronger role-aware auth boundaries for admin-only APIs.',
                'CSRF review for JSON endpoints and narrower exemption surface.',
                'Audit logging expansion for all state changes.',
            ],
        },
        {
            'priority': 'P1',
            'title': 'Paperwork elimination core',
            'items': [
                'Case intake wizard with mandatory document checklist.',
                'Digital affidavit/e-filing packets with field validation.',
                'Role-based task queues for intake, review, and closure.',
            ],
        },
        {
            'priority': 'P2',
            'title': 'Intelligence and automation',
            'items': [
                'OCR extraction for uploaded legal documents.',
                'Auto-drafted notices and summary sheets.',
                'Timeline reminders and SLA dashboards.',
            ],
        },
        {
            'priority': 'P3',
            'title': 'Compliance and interoperability',
            'items': [
                'Tamper-evident document hashing in audit records.',
                'Digital signature workflow for approvals.',
                'Interoperable import/export adapters.',
            ],
        },
    ]

    return render_template(
        'admin_dev_guide.html',
        backend_modules=backend_modules,
        api_inventory=api_inventory,
        db_schema=db_schema,
        db_schema_source=schema_source,
        template_files=templates,
        static_items=static_items,
        realtime_notes=realtime_notes,
        runbook=runbook,
        known_risks=known_risks,
        backlog=backlog,
    )

@app.route('/admin/api/applications')
def admin_api_applications():
    if not is_admin_authenticated():
        return jsonify({'error': 'Access denied'}), 403
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM lawyer_applications WHERE status='pending'")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)

@app.route('/admin/api/users')
def admin_api_users():
    if not is_admin_authenticated():
        return jsonify({'error': 'Access denied'}), 403
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name, email, phone, created_at FROM users ORDER BY created_at DESC")
    users = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(users)

@app.route('/admin/api/lawyers')
def admin_api_lawyers():
    if not is_admin_authenticated():
        return jsonify({'error': 'Access denied'}), 403
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name, email, phone, specialization, years_experience, status, created_at FROM lawyers ORDER BY created_at DESC")
    lawyers = cur.fetchall()
    cur.close(); conn.close()
    return jsonify(lawyers)

@app.route('/admin/users')
def admin_users():
    """Admin page to view all users"""
    if not is_admin_authenticated():
        return redirect(url_for('admin_login'))
    return render_template('admin_users.html')

@app.route('/admin/cases')
def admin_cases():
    """Admin page to view all user cases"""
    if not is_admin_authenticated():
        return redirect(url_for('admin_login'))
    return render_template('admin_cases.html')

@app.route('/admin/lawyers')
def admin_lawyers():
    """Admin page to view all lawyers"""
    if not is_admin_authenticated():
        return redirect(url_for('admin_login'))
    return render_template('admin_lawyers.html')

@app.route('/admin/api/user-cases')
def admin_api_user_cases():
    """API endpoint to get all user cases with user and lawyer details"""
    if not is_admin_authenticated():
        return jsonify({'error': 'Access denied'}), 403
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor(dictionary=True)
        query = """
        SELECT 
            uc.id,
            uc.case_title,
            uc.case_type,
            uc.case_description,
            uc.case_status,
            uc.priority,
            uc.budget_range,
            uc.timeline,
            uc.incident_date,
            uc.location,
            uc.created_at,
            uc.updated_at,
            u.name as user_name,
            u.email as user_email,
            u.phone as user_phone,
            l.name as lawyer_name,
            l.email as lawyer_email,
            l.specialization as lawyer_specialization
        FROM user_cases uc
        LEFT JOIN users u ON uc.user_id = u.id
        LEFT JOIN lawyers l ON uc.lawyer_id = l.id
        ORDER BY uc.created_at DESC
        """
        cur.execute(query)
        cases = cur.fetchall()
        
        # Convert JSON fields
        for case in cases:
            if case.get('documents'):
                try:
                    case['documents'] = json.loads(case['documents'])
                except:
                    case['documents'] = []
            else:
                case['documents'] = []
        
        cur.close()
        conn.close()
        return jsonify(cases)
        
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@app.route('/admin/api/users-detailed')
def admin_api_users_detailed():
    """API endpoint to get all users with their case counts"""
    if not is_admin_authenticated():
        return jsonify({'error': 'Access denied'}), 403
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    
    try:
        cur = conn.cursor(dictionary=True)
        query = """
        SELECT 
            u.id,
            u.name,
            u.email,
            u.phone,
            u.created_at,
            COUNT(uc.id) as total_cases,
            COUNT(CASE WHEN uc.case_status = 'open' THEN 1 END) as open_cases,
            COUNT(CASE WHEN uc.case_status = 'in_progress' THEN 1 END) as in_progress_cases,
            COUNT(CASE WHEN uc.case_status = 'closed' THEN 1 END) as closed_cases
        FROM users u
        LEFT JOIN user_cases uc ON u.id = uc.user_id
        GROUP BY u.id, u.name, u.email, u.phone, u.created_at
        ORDER BY u.created_at DESC
        """
        cur.execute(query)
        users = cur.fetchall()
        
        cur.close()
        conn.close()
        return jsonify(users)
        
    except Exception as e:
        if conn:
            conn.close()
        return jsonify({'error': f'Database error: {str(e)}'}), 500

@app.route('/api/contact-messages')
def get_contact_messages():
    """Get all contact messages"""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500
    
    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM contact_messages ORDER BY created_at DESC"
        cursor.execute(query)
        messages = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'messages': messages
        })
        
    except Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/lawyer-applications')
def get_lawyer_applications():
    """Get all lawyer applications"""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    connection = get_db_connection()
    if not connection:
        # Use fallback storage when database is not available
        applications = get_lawyer_applications_fallback()
        return jsonify({
            'success': True,
            'applications': applications
        })
    
    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM lawyer_applications ORDER BY created_at DESC"
        cursor.execute(query)
        applications = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'applications': applications
        })
        
    except Error as e:
        # Fallback to in-memory storage on database error
        applications = get_lawyer_applications_fallback()
        return jsonify({
            'success': True,
            'applications': applications
        })
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/applications/<int:application_id>')
def get_application(application_id):
    """Get specific application by ID"""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500
    
    try:
        cursor = connection.cursor(dictionary=True)
        query = "SELECT * FROM lawyer_applications WHERE id = %s"
        cursor.execute(query, (application_id,))
        application = cursor.fetchone()
        
        if application:
            return jsonify({
                'success': True,
                'application': application
            })
        else:
            return jsonify({'success': False, 'error': 'Application not found'}), 404
            
    except Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/applications/<int:application_id>/status', methods=['PUT'])
@csrf.exempt
def update_application_status(application_id):
    """Enhanced application status update with automatic lawyer creation"""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500
    
    try:
        data = request.get_json()
        status = data.get('status')
        reason = data.get('reason', '').strip()
        processed_by = data.get('processed_by', 'Admin')
        
        if status not in ['approved', 'rejected']:
            return jsonify({'success': False, 'error': 'Invalid status. Must be approved or rejected'}), 400
        
        cursor = connection.cursor(dictionary=True)
        
        # Get current application details
        cursor.execute("SELECT * FROM lawyer_applications WHERE id = %s", (application_id,))
        application = cursor.fetchone()
        
        if not application:
            return jsonify({'success': False, 'error': 'Application not found'}), 404
        
        if application['status'] != 'pending':
            return jsonify({'success': False, 'error': f'Application already {application["status"]}'}), 400
        
        old_status = application['status']
        
        success_message = f'Application {status} successfully!'
        lawyer_id = None
        
        # If approved, create lawyer profile first then mark application approved (no rollback to pending)
        if status == 'approved':
            try:
                # Check for existing lawyer with same email
                if check_duplicate_lawyer(application['email'], application['phone']):
                    return jsonify({
                        'success': False, 
                        'error': 'A lawyer with this email or phone number already exists'
                    }), 400
                
                # Create lawyer profile
                lawyer_id = create_lawyer_from_application(application)
                
                if lawyer_id:
                    success_message += f' Lawyer profile created successfully (ID: {lawyer_id}).'
                    # Mark application as approved now
                    cursor.execute("""
                        UPDATE lawyer_applications 
                        SET status = 'approved', rejection_reason = NULL, processed_by = %s, processed_at = NOW(), updated_at = NOW() 
                        WHERE id = %s
                    """, (processed_by, application_id))
                    connection.commit()
                    
                    # Send approval email (optional)
                    approval_email_body = f"""
                    <html><body>
                        <h2>Congratulations!</h2>
                        <p>Dear {application['name']}, your application has been <strong>approved</strong>.</p>
                        <p>Your profile is live and visible to clients.</p>
                        <p>Details: {application['specialization']} • {application['years_experience']} years • {application['location']}</p>
                        <p>- LegalMatch Team</p>
                    </body></html>
                    """
                    if SEND_APPROVAL_EMAIL:
                        send_email(
                            application['email'], 
                            "LegalMatch Application Approved - Welcome!",
                            approval_email_body
                        )
                    
                else:
                    return jsonify({
                        'success': False, 
                        'error': 'Failed to create lawyer profile. Please try again.'
                    }), 500
                    
            except Exception as e:
                print(f"Error during lawyer creation: {e}")
                return jsonify({
                    'success': False, 
                    'error': f'Error creating lawyer profile: {str(e)}'
                }), 500
        
        # If rejected, send rejection email
        elif status == 'rejected':
            cursor.execute("""
                UPDATE lawyer_applications 
                SET status = 'rejected', rejection_reason = %s, processed_by = %s, processed_at = NOW(), updated_at = NOW() 
                WHERE id = %s
            """, (reason, processed_by, application_id))
            connection.commit()
            rejection_email_body = f"""
            <html><body>
                <h2>Application Update</h2>
                <p>Dear {application['name']}, your application was <strong>rejected</strong>.</p>
                {f'<p>Reason: {reason}</p>' if reason else ''}
                <p>You can reapply after addressing the reason above.</p>
                <p>- LegalMatch Team</p>
            </body></html>
            """
            if SEND_REJECTION_EMAIL:
                send_email(
                    application['email'], 
                    "LegalMatch Application Update",
                    rejection_email_body
                )
        
        # Log the action
        log_application_action(
            application_id, 
            f'status_changed_to_{status}', 
            old_status, 
            status, 
            reason, 
            processed_by
        )
        
        connection.commit()
        
        response_data = {
            'success': True, 
            'message': success_message,
            'application_id': application_id,
            'new_status': status
        }
        
        if lawyer_id:
            response_data['lawyer_id'] = lawyer_id
        
        return jsonify(response_data)
        
    except Error as e:
        print(f"Database error in update_application_status: {e}")
        if connection.is_connected():
            connection.rollback()
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        print(f"General error in update_application_status: {e}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/applications/<int:application_id>', methods=['DELETE'])
def delete_application(application_id):
    """Delete an application"""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500
    
    try:
        cursor = connection.cursor()
        query = "DELETE FROM lawyer_applications WHERE id = %s"
        cursor.execute(query, (application_id,))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Application not found'}), 404
        
        connection.commit()
        return jsonify({'success': True, 'message': 'Application deleted successfully'})
        
    except Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/messages/<int:message_id>/status', methods=['PUT'])
def update_message_status(message_id):
    """Update contact message status"""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500
    
    try:
        data = request.get_json()
        status = data.get('status')
        
        if status not in ['new', 'read', 'replied']:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        cursor = connection.cursor()
        query = "UPDATE contact_messages SET status = %s WHERE id = %s"
        cursor.execute(query, (status, message_id))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Message not found'}), 404
        
        connection.commit()
        return jsonify({'success': True, 'message': f'Message status updated to {status}'})
        
    except Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/messages/<int:message_id>', methods=['DELETE'])
def delete_message(message_id):
    """Delete a contact message"""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500
    
    try:
        cursor = connection.cursor()
        query = "DELETE FROM contact_messages WHERE id = %s"
        cursor.execute(query, (message_id,))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Message not found'}), 404
        
        connection.commit()
        return jsonify({'success': True, 'message': 'Message deleted successfully'})
        
    except Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/admin/stats')
def get_admin_stats():
    """Get admin dashboard statistics"""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500
    
    try:
        cursor = connection.cursor(dictionary=True)
        
        # Get counts for different entities
        stats = {}
        
        # Total verified lawyers
        cursor.execute("SELECT COUNT(*) as count FROM lawyers WHERE status = 'verified'")
        stats['verified_lawyers'] = cursor.fetchone()['count']
        
        # Pending applications
        cursor.execute("SELECT COUNT(*) as count FROM lawyer_applications WHERE status = 'pending'")
        stats['pending_applications'] = cursor.fetchone()['count']
        
        # New contact messages
        cursor.execute("SELECT COUNT(*) as count FROM contact_messages WHERE status = 'new'")
        stats['new_messages'] = cursor.fetchone()['count']
        
        # Total contact messages
        cursor.execute("SELECT COUNT(*) as count FROM contact_messages")
        stats['total_messages'] = cursor.fetchone()['count']
        
        # Average rating
        cursor.execute("SELECT AVG(rating) as avg_rating FROM lawyers WHERE status = 'verified' AND total_ratings > 0")
        result = cursor.fetchone()
        stats['average_rating'] = round(float(result['avg_rating'] or 0), 1)
        
        # Lawyers by specialization
        cursor.execute("""
        SELECT specialization, COUNT(*) as count 
        FROM lawyers 
        WHERE status = 'verified' 
        GROUP BY specialization
        """)
        stats['specialization_distribution'] = cursor.fetchall()
        
        # Recent activities (last 10)
        cursor.execute("""
        SELECT 'lawyer' as type, name as title, created_at, 'registered' as action
        FROM lawyers 
        WHERE status = 'verified'
        UNION ALL
        SELECT 'application' as type, name as title, created_at, 'applied' as action
        FROM lawyer_applications
        UNION ALL
        SELECT 'message' as type, name as title, created_at, 'contacted' as action
        FROM contact_messages
        ORDER BY created_at DESC
        LIMIT 10
        """)
        stats['recent_activities'] = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

