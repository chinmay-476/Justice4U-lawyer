from flask import render_template, request, jsonify, redirect, url_for, flash, send_from_directory
import os
import json
import uuid
from datetime import datetime
from mysql.connector import Error
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from core import app, csrf, limiter, EMAIL_CONFIG, send_email, get_db_connection, is_admin_authenticated, get_current_lawyer_id, sanitize_input, validate_email, validate_phone, sanitize_phone, normalize_indian_phone, allowed_file, add_contact_message, add_lawyer_application, add_lawyer_application_fallback, get_lawyer_by_id, add_lawyer_to_db, add_rating, get_all_lawyers_from_db, get_lawyer_applications_fallback, create_lawyer_from_application, log_application_action, SEND_APPROVAL_EMAIL, SEND_REJECTION_EMAIL, UPLOAD_FOLDER
from config import MAX_FILE_SIZE

def _require_admin_api():
    if not is_admin_authenticated():
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    return None

@app.route('/')
def home():
    return render_template('home.html', hide_chrome=True)

@app.route('/api/health')
def health_check():
    return jsonify({'success': True, 'status': 'ok', 'timestamp': datetime.utcnow().isoformat() + 'Z'})

@app.route('/auth-center')
def auth_center():
    return render_template('auth_center.html', hide_chrome=True)

@app.route('/lawyers')
def lawyers():
    lawyers = get_all_lawyers_from_db()
    return render_template('lawyers.html', lawyers=lawyers)

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/contact', methods=['POST'])
@limiter.limit("5 per minute")
def submit_contact():
    try:
        contact_data = {
            'name': sanitize_input(request.form['name']),
            'email': sanitize_input(request.form['email']),
            'message': sanitize_input(request.form['message']),
            'phone': sanitize_input(request.form.get('phone', '')),
            'subject': sanitize_input(request.form.get('subject', 'general')),
            'legal_area': sanitize_input(request.form.get('legal_area', '')),
            'urgency': sanitize_input(request.form.get('urgency', 'low'))
        }
        
        # Enhanced validation
        required_fields = ['name', 'email', 'message']
        if not all([contact_data[field] for field in required_fields]):
            flash('Name, email, and message are required fields', 'error')
            return render_template('contact.html', data=contact_data)
        
        # Validate email format
        if not validate_email(contact_data['email']):
            flash('Please enter a valid email address.', 'error')
            return render_template('contact.html', data=contact_data)
        
        # Validate phone if provided
        if contact_data['phone'] and not validate_phone(contact_data['phone']):
            flash('Please enter a valid phone number.', 'error')
            return render_template('contact.html', data=contact_data)
        
        
        # Message length validation
        if len(contact_data['message']) < 10:
            flash('Message must be at least 10 characters long', 'error')
            return render_template('contact.html', data=contact_data)
        
        if len(contact_data['message']) > 1000:
            flash('Message must be less than 1000 characters', 'error')
            return render_template('contact.html', data=contact_data)
        
        if add_contact_message(contact_data):
            flash('Thank you for your message! We will get back to you soon.', 'success')
            return redirect(url_for('contact'))
        else:
            flash('Error sending message. Please try again.', 'error')
            return render_template('contact.html', data=contact_data)
            
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return render_template('contact.html')

@app.route('/apply')
def lawyer_registration():
    return render_template('lawyer_registration.html')

@app.route('/apply', methods=['POST'])
@limiter.limit("3 per hour")
def submit_application():
    try:
        phone_raw = sanitize_input(request.form['phone'])
        phone_clean = sanitize_phone(phone_raw)

        application_data = {
            'name': sanitize_input(request.form['name']),
            'email': sanitize_input(request.form['email']).lower(),
            'phone': normalize_indian_phone(phone_clean),
            'license_number': sanitize_input(request.form['license_number']),
            'degree': sanitize_input(request.form['degree']),
            'specialization': sanitize_input(request.form['specialization']),
            'years_experience': int(request.form['years_experience']),
            'bio': sanitize_input(request.form['bio']),
            'location': sanitize_input(request.form['location']),
            'state': sanitize_input(request.form.get('state', '')),
            'district': sanitize_input(request.form.get('district', '')),
            'pincode': sanitize_input(request.form.get('pincode', '')),
            'consultation_fee': float(request.form.get('consultation_fee', 0)),
            'case_fee_range': sanitize_input(request.form.get('case_fee_range', ''))
        }

        if not validate_phone(phone_clean):
            flash('Please enter a valid phone number.', 'error')
            application_data['phone'] = phone_raw  # Show original input on error
            return render_template('lawyer_registration.html', data=application_data)

        # Handle file uploads
        document_path = None
        photo_path = None
        
        # Handle document upload
        if 'document' in request.files:
            file = request.files['document']
            if file and file.filename and allowed_file(file.filename):
                # Check file size
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)

                if file_size <= MAX_FILE_SIZE:
                    filename = secure_filename(file.filename)
                    file_ext = filename.rsplit('.', 1)[1].lower()
                    unique_filename = f"{uuid.uuid4().hex}.{file_ext}"
                    file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                    file.save(file_path)
                    application_data['document_path'] = file_path
                else:
                    flash('Document file size must be less than 5MB', 'error')
                    return render_template('lawyer_registration.html', data=application_data)
        
        # Handle photo upload
        if 'photo' in request.files:
            photo = request.files['photo']
            if photo and photo.filename:
                # Validate image file
                if not photo.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
                    flash('Photo must be a valid image file (JPG, PNG, GIF)', 'error')
                    return render_template('lawyer_registration.html', data=application_data)
                
                # Check file size (2MB max for photos)
                photo.seek(0, os.SEEK_END)
                photo_size = photo.tell()
                photo.seek(0)

                if photo_size <= 2 * 1024 * 1024:  # 2MB max
                    filename = secure_filename(photo.filename)
                    file_ext = filename.rsplit('.', 1)[1].lower()
                    unique_filename = f"photo_{uuid.uuid4().hex}.{file_ext}"
                    photo_file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                    photo.save(photo_file_path)
                    application_data['photo_path'] = photo_file_path
                else:
                    flash('Photo file size must be less than 2MB', 'error')
                    return render_template('lawyer_registration.html', data=application_data)
                    
        # Enhanced validation
        required_fields = ['name', 'email', 'phone', 'license_number', 'degree', 'specialization', 'bio', 'location']
        if not all([application_data[field] for field in required_fields]):
            flash('All fields are required', 'error')
            return render_template('lawyer_registration.html', data=application_data)
        
        # Validate email format
        if not validate_email(application_data['email']):
            flash('Please enter a valid email address.', 'error')
            return render_template('lawyer_registration.html', data=application_data)
        
        # Validate phone format again to be safe
        if not validate_phone(application_data['phone']):
            flash('Please enter a valid phone number.', 'error')
            return render_template('lawyer_registration.html', data=application_data)
        
        if application_data['years_experience'] < 0:
            flash('Years of experience cannot be negative', 'error')
            return render_template('lawyer_registration.html', data=application_data)
        
        if len(application_data['bio']) < 50:
            flash('Bio must be at least 50 characters long', 'error')
            return render_template('lawyer_registration.html', data=application_data)
        
        application_id = add_lawyer_application(application_data)
        
        if application_id:
            flash('Application submitted successfully! We will review your application and get back to you within 5-7 business days.', 'success')
            
            # Send confirmation email to applicant
            confirmation_email = f"""
            <html>
            <body>
                <h2>Application Received</h2>
                <p>Dear {application_data['name']},</p>
                
                <p>Thank you for applying to join LegalMatch. We have received your application and it is currently under review.</p>
                
                <p><strong>Application Summary:</strong></p>
                <ul>
                    <li>Application ID: #{application_id}</li>
                    <li>Specialization: {application_data['specialization']}</li>
                    <li>Experience: {application_data['years_experience']} years</li>
                    <li>Location: {application_data['location']}</li>
                    <li>Submitted: {datetime.now().strftime('%B %d, %Y')}</li>
                </ul>
                
                <p>We will review your application within 5-7 business days and notify you of our decision.</p>
                
                <p>Best regards,<br>
                LegalMatch Team</p>
            </body>
            </html>
            """
            
            send_email(
                application_data['email'],
                "LegalMatch Application Received",
                confirmation_email
            )
            
            return redirect(url_for('lawyer_registration'))
        else:
            # If database is not available, store in memory as fallback
            application_id = add_lawyer_application_fallback(application_data)
            if application_id:
                flash('Application submitted successfully! (Note: Database temporarily unavailable, but your application has been recorded.)', 'success')
                return redirect(url_for('lawyer_registration'))
            else:
                flash('Error submitting application. Please try again.', 'error')
                return render_template('lawyer_registration.html', data=application_data)
            
    except ValueError:
        flash('Invalid input: Please check your data', 'error')
        return render_template('lawyer_registration.html')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return render_template('lawyer_registration.html')

@app.route('/lawyer/<int:lawyer_id>')
def lawyer_detail(lawyer_id):
    lawyer = get_lawyer_by_id(lawyer_id)
    if not lawyer:
        flash('Lawyer not found', 'error')
        return redirect(url_for('lawyers'))
    return render_template('lawyer_details.html', lawyer=lawyer)

@app.route('/add-lawyer')
def add_lawyer_form():
    return render_template('add_lawyer.html')

@app.route('/add-lawyer', methods=['POST'])
def add_lawyer():
    try:
        lawyer_data = {
            'name': request.form['name'].strip(),
            'specialization': request.form['specialization'].strip(),
            'years_experience': int(request.form['years_experience']),
            'rating': float(request.form['rating']),
            'bio': request.form['bio'].strip(),
            'photo': request.form['photo'].strip() or 'https://via.placeholder.com/300x300/3730a3/ffffff?text=Lawyer',
            'phone': request.form['phone'].strip(),
            'email': request.form['email'].strip(),
            'location': request.form['location'].strip(),
            'keywords': [keyword.strip().lower() for keyword in request.form['keywords'].split(',') if keyword.strip()]
        }
        
        if not all([lawyer_data['name'], lawyer_data['specialization'], lawyer_data['bio'],
                   lawyer_data['phone'], lawyer_data['email'], lawyer_data['location']]):
            flash('All fields are required', 'error')
            return render_template('add_lawyer.html', data=lawyer_data)
        
        if not (0 <= lawyer_data['rating'] <= 5):
            flash('Rating must be between 0 and 5', 'error')
            return render_template('add_lawyer.html', data=lawyer_data)
        
        if lawyer_data['years_experience'] < 0:
            flash('Years of experience cannot be negative', 'error')
            return render_template('add_lawyer.html', data=lawyer_data)
        
        lawyer_id = add_lawyer_to_db(lawyer_data)
        
        if lawyer_id:
            flash('Lawyer added successfully!', 'success')
            return redirect(url_for('lawyer_detail', lawyer_id=lawyer_id))
        else:
            flash('Error adding lawyer to database', 'error')
            return render_template('add_lawyer.html', data=lawyer_data)
            
    except ValueError:
        flash('Invalid input: Please check your data', 'error')
        return render_template('add_lawyer.html')
    except Exception as e:
        flash(f'An error occurred: {str(e)}', 'error')
        return render_template('add_lawyer.html')

@app.route('/api/rate-lawyer', methods=['POST'])
@csrf.exempt
def rate_lawyer():
    try:
        data = request.get_json()
        lawyer_id = data.get('lawyer_id')
        rating = data.get('rating')
        user_ip = request.remote_addr
        
        if not lawyer_id or not rating:
            return jsonify({'error': 'Lawyer ID and rating are required'}), 400
        
        if not (1 <= rating <= 5):
            return jsonify({'error': 'Rating must be between 1 and 5'}), 400
        
        if add_rating(lawyer_id, rating, user_ip):
            # Get updated lawyer info
            lawyer = get_lawyer_by_id(lawyer_id)
            return jsonify({
                'success': True,
                'new_rating': float(lawyer['rating']),
                'total_ratings': lawyer['total_ratings']
            })
        else:
            return jsonify({'error': 'Error saving rating'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/lawyers')
def get_all_lawyers_api():
    try:
        specialty = request.args.get('specialty', '').lower()
        sort_by = request.args.get('sort', 'rating')
        search = request.args.get('search', '').lower()
        
        lawyers = get_all_lawyers_from_db()
        
        # Filter by search term
        if search:
            lawyers = [l for l in lawyers if
                      search in l['name'].lower() or
                      search in l['specialization'].lower() or
                      search in l['location'].lower()]
        
        # Filter by specialty
        if specialty:
            lawyers = [l for l in lawyers if specialty in l['specialization'].lower()]
        
        # Sort lawyers
        if sort_by == 'experience':
            lawyers.sort(key=lambda x: x['years_experience'], reverse=True)
        elif sort_by == 'name':
            lawyers.sort(key=lambda x: x['name'])
        else:
            lawyers.sort(key=lambda x: float(x['rating']), reverse=True)
        
        return jsonify({
            'success': True,
            'lawyers': lawyers
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/lawyers/<int:lawyer_id>')
def get_lawyer_api(lawyer_id):
    """Get specific lawyer by ID"""
    lawyer = get_lawyer_by_id(lawyer_id)
    if lawyer:
        return jsonify({
            'success': True,
            'lawyer': lawyer
        })
    else:
        return jsonify({'success': False, 'error': 'Lawyer not found'}), 404

@app.route('/api/lawyers/<int:lawyer_id>', methods=['PUT'])
def update_lawyer(lawyer_id):
    """Update lawyer information"""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500
    
    try:
        data = request.get_json()
        cursor = connection.cursor()
        
        # Validate required fields
        required_fields = ['name', 'email', 'specialization', 'years_experience', 'bio']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field} is required'}), 400
        
        query = """
        UPDATE lawyers 
        SET name = %s, email = %s, specialization = %s, years_experience = %s, bio = %s, updated_at = NOW()
        WHERE id = %s
        """
        
        values = (
            data['name'].strip(),
            data['email'].strip(),
            data['specialization'].strip(),
            int(data['years_experience']),
            data['bio'].strip(),
            lawyer_id
        )
        
        cursor.execute(query, values)
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Lawyer not found'}), 404
        
        connection.commit()
        return jsonify({'success': True, 'message': 'Lawyer updated successfully'})
        
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid data format'}), 400
    except Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/lawyers/<int:lawyer_id>', methods=['DELETE'])
def delete_lawyer(lawyer_id):
    """Delete a lawyer"""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500
    
    try:
        cursor = connection.cursor()
        query = "DELETE FROM lawyers WHERE id = %s"
        cursor.execute(query, (lawyer_id,))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Lawyer not found'}), 404
        
        connection.commit()
        return jsonify({'success': True, 'message': 'Lawyer deleted successfully'})
        
    except Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/api/lawyers/<int:lawyer_id>/status', methods=['PUT'])
def update_lawyer_status(lawyer_id):
    """Update lawyer status"""
    auth_error = _require_admin_api()
    if auth_error:
        return auth_error
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500
    
    try:
        data = request.get_json()
        status = data.get('status')
        
        if status not in ['verified', 'pending', 'rejected']:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400
        
        cursor = connection.cursor()
        query = "UPDATE lawyers SET status = %s, updated_at = NOW() WHERE id = %s"
        cursor.execute(query, (status, lawyer_id))
        
        if cursor.rowcount == 0:
            return jsonify({'success': False, 'error': 'Lawyer not found'}), 404
        
        connection.commit()
        return jsonify({'success': True, 'message': f'Lawyer status updated to {status}'})
        
    except Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/verify-email')
def verify_email():
    token = request.args.get('token', '').strip()
    if not token:
        return jsonify({'success': False, 'error': 'Missing token'}), 400
    connection = get_db_connection()
    if not connection:
        return jsonify({'success': False, 'error': 'Database connection failed'}), 500
    try:
        cursor = connection.cursor(dictionary=True)
        # Find valid token
        cursor.execute("SELECT lawyer_id FROM verification_tokens WHERE token = %s AND expires_at > NOW()", (token,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 400

        lawyer_id = row['lawyer_id']
        # Activate lawyer
        cursor.execute("UPDATE lawyers SET status = 'verified', updated_at = NOW() WHERE id = %s", (lawyer_id,))
        # Remove token
        cursor.execute("DELETE FROM verification_tokens WHERE token = %s", (token,))
        connection.commit()
        return jsonify({'success': True, 'message': 'Email verified. Profile activated.'})
    except Error as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/manifest.json')
def manifest():
    """Serve PWA manifest with proper headers"""
    response = send_from_directory('static', 'manifest.json')
    response.headers['Content-Type'] = 'application/manifest+json'
    response.headers['Cache-Control'] = 'public, max-age=86400'  # Cache for 1 day
    return response

@app.route('/service-worker.js')
def service_worker():
    """Serve service worker with proper headers"""
    response = send_from_directory('static', 'service-worker.js')
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'  # Don't cache service worker
    response.headers['Service-Worker-Allowed'] = '/'
    return response

@app.route('/static/icons/<path:filename>')
def serve_icons(filename):
    """Serve PWA icons with proper headers"""
    response = send_from_directory('static/icons', filename)
    
    # Set appropriate content type based on file extension
    if filename.endswith('.png'):
        response.headers['Content-Type'] = 'image/png'
    elif filename.endswith('.svg'):
        response.headers['Content-Type'] = 'image/svg+xml'
    elif filename.endswith('.ico'):
        response.headers['Content-Type'] = 'image/x-icon'
    
    # Cache icons for 1 week
    response.headers['Cache-Control'] = 'public, max-age=604800'
    return response

@app.route('/api/lawyers/<int:lawyer_id>/messages', methods=['POST'])
@csrf.exempt
def submit_message_to_lawyer(lawyer_id):
    connection = None
    try:
        # Handle both JSON and FormData requests
        if request.is_json:
            data = request.get_json() or {}
            client_name = sanitize_input(data.get('client_name', ''))
            client_email = sanitize_input(data.get('client_email', ''))
            client_phone = normalize_indian_phone(sanitize_input(data.get('client_phone', '')))
            message = sanitize_input(data.get('message', ''))
            uploaded_files = []
        else:
            # Handle FormData (with file uploads)
            client_name = sanitize_input(request.form.get('client_name', ''))
            client_email = sanitize_input(request.form.get('client_email', ''))
            client_phone = normalize_indian_phone(sanitize_input(request.form.get('client_phone', '')))
            message = sanitize_input(request.form.get('message', ''))
            
            # Handle uploaded documents
            uploaded_files = []
            files = request.files.getlist('documents')
            for file in files:
                if file and file.filename:
                    # Validate file type
                    if not file.filename.lower().endswith(('.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png')):
                        continue
                    
                    # Check file size (10MB max)
                    file.seek(0, os.SEEK_END)
                    file_size = file.tell()
                    file.seek(0)
                    
                    if file_size <= 10 * 1024 * 1024:  # 10MB max
                        filename = secure_filename(file.filename)
                        file_ext = filename.rsplit('.', 1)[1].lower()
                        unique_filename = f"client_doc_{uuid.uuid4().hex}.{file_ext}"
                        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
                        file.save(file_path)
                        uploaded_files.append({
                            'original_name': filename,
                            'saved_path': file_path,
                            'size': file_size
                        })
        
        if not client_name or not client_email or not message:
            return jsonify({'success': False, 'error': 'client_name, client_email and message are required'}), 400
        
        connection = get_db_connection()
        if not connection:
            return jsonify({'success': False, 'error': 'Database connection failed'}), 500
        
        cursor = connection.cursor()
        
        # Add file information to message if files were uploaded
        if uploaded_files:
            file_info = "\n\nUploaded Documents:\n"
            for file in uploaded_files:
                file_info += f"- {file['original_name']} ({(file['size'] / 1024 / 1024):.2f} MB)\n"
            message += file_info
        
        cursor.execute("""
            INSERT INTO lawyer_client_messages (lawyer_id, client_name, client_email, client_phone, message)
            VALUES (%s, %s, %s, %s, %s)
        """, (lawyer_id, client_name, client_email, client_phone or None, message))
        connection.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        try:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()
        except Exception:
            pass

@app.route('/api/states')
def get_states():
    """Get all Indian states"""
    try:
        with open('static/data/indian_states_districts.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        states = list(data['states'].keys())
        return jsonify({
            'success': True,
            'states': states
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/districts/<state>')
def get_districts(state):
    """Get districts for a specific state"""
    try:
        with open('static/data/indian_states_districts.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if state in data['states']:
            districts = data['states'][state]
            return jsonify({
                'success': True,
                'districts': districts
            })
        else:
            return jsonify({'success': False, 'error': 'State not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/lawyers/search')
def search_lawyers():
    """Advanced lawyer search with multiple filters"""
    try:
        # Get query parameters
        query = request.args.get('q', '').lower()
        specialization = request.args.get('specialization', '')
        min_experience = request.args.get('min_experience', 0, type=int)
        max_experience = request.args.get('max_experience', 100, type=int)
        min_rating = request.args.get('min_rating', 0, type=float)
        location = request.args.get('location', '').lower()
        sort_by = request.args.get('sort', 'rating')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        lawyers = get_all_lawyers_from_db('verified')
        
        # Apply filters
        filtered_lawyers = []
        for lawyer in lawyers:
            # Text search in name, bio, specialization
            if query and not any(query in str(lawyer[field]).lower() 
                               for field in ['name', 'bio', 'specialization'] if lawyer[field]):
                continue
            
            # Specialization filter
            if specialization and specialization.lower() not in lawyer['specialization'].lower():
                continue
            
            # Experience range filter
            if not (min_experience <= lawyer['years_experience'] <= max_experience):
                continue
            
            # Rating filter
            if lawyer['rating'] < min_rating:
                continue
            
            # Location filter
            if location and location not in lawyer['location'].lower():
                continue
            
            filtered_lawyers.append(lawyer)
        
        # Sort results
        if sort_by == 'name':
            filtered_lawyers.sort(key=lambda x: x['name'])
        elif sort_by == 'experience':
            filtered_lawyers.sort(key=lambda x: x['years_experience'], reverse=True)
        elif sort_by == 'rating':
            filtered_lawyers.sort(key=lambda x: float(x['rating']), reverse=True)
        elif sort_by == 'recent':
            filtered_lawyers.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        # Pagination
        total = len(filtered_lawyers)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_lawyers = filtered_lawyers[start:end]
        
        return jsonify({
            'success': True,
            'lawyers': paginated_lawyers,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page
            },
            'filters_applied': {
                'query': query,
                'specialization': specialization,
                'min_experience': min_experience,
                'max_experience': max_experience,
                'min_rating': min_rating,
                'location': location,
                'sort_by': sort_by
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

