import os
import json
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import func, or_

from config import Config, BASE_DIR
from models import db, User, Customer, Prescription, Supplier, Frame, Lens, Order, Invoice, Payment, InventoryTransaction
from utils.helpers import (
    admin_required, generate_customer_code, generate_order_number,
    generate_invoice_number, generate_frame_code, generate_lens_code, save_uploaded_file
)
from utils.pdf_generator import generate_invoice_pdf, generate_report_pdf
from utils.excel_exporter import generate_report_excel
from utils.app_meta import APP_NAME, APP_TAGLINE, DEVELOPER_NAME, DEVELOPER_CONTACT, get_run_count
from utils.license_manager import get_license_status, verify_license_key, save_license, generate_system_id
from billing_models import InvoiceItem, get_bill_items, ensure_invoice_order_nullable
from bill_pdf import generate_bill_pdf

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, make_response, session
import secrets
from datetime import datetime, timedelta
from flask import session

from flask import abort, flash, redirect, url_for
from flask_login import login_required, current_user

def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, 'templates'),
        static_folder=os.path.join(BASE_DIR, 'static'),
    )
    
    app.config.from_object(Config)
    
    
    app.config["APP_START_TOKEN"] = secrets.token_hex(16)
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=2)
    app.config["SESSION_REFRESH_EACH_REQUEST"] = True

    db.init_app(app)
    with app.app_context():
        db.create_all()  # creates the new invoice_items table on existing databases
        ensure_invoice_order_nullable(db)  # lets bills exist without an order
        print("DATABASE USED BY FLASK:")
        print(db.engine.url.database)
        print("FRAME COUNT:")
        print(Frame.query.count())
        
    login_manager = LoginManager()
    login_manager.login_view = 'login'
    login_manager.login_message_category = 'info'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_active_page():
        return dict(active_page=request.endpoint)

    # ---------------------------------------------------------
    # LICENSE GATE
    # Every request re-checks the license. When it is missing or
    # expired, everything except static files and the license page
    # itself redirects to the activation / renewal page.
    # ---------------------------------------------------------
    @app.before_request
    def enforce_license():
        if request.endpoint in (None, 'static', 'license_page'):
            return None
        if not get_license_status()['activated']:
            return redirect(url_for('license_page'))
        return None

    @app.route('/license', methods=['GET', 'POST'])
    def license_page():
        if request.method == 'POST':
            key = request.form.get('license_key', '').strip()
            result = verify_license_key(key) if key else {'valid': False, 'error': 'Please paste your license key.'}
            if result['valid']:
                save_license(key)
                flash(f"License activated successfully. Valid until {result['expiry_date']}.", 'success')
                return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('login'))
            flash(result['error'], 'danger')
            return redirect(url_for('license_page'))
        return render_template('license.html', status=get_license_status(), system_id=generate_system_id())

    # ---------------------------------------------------------
    # AUTHENTICATION ROUTES
    # ---------------------------------------------------------

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            login_input = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()

            user = User.query.filter(
                or_(
                    User.username == login_input,
                    User.email == login_input
                )
            ).first()

            if user and user.check_password(password):
                if not user.is_active:
                    flash(
                        'This user account has been deactivated. Please contact an administrator.',
                        'danger'
                    )
                    return redirect(url_for('login'))

                login_user(user)

                # Set the 2-minute session timeout
                session.permanent = True
                session["app_start_token"] = app.config["APP_START_TOKEN"]
                session["last_activity"] = datetime.utcnow().timestamp()

                flash(f'Welcome back, {user.name}!', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('dashboard'))

            flash(
                'Invalid Username/Email or Password. Please try again.',
                'danger'
            )

        return render_template('login.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()
            role = request.form.get('role', 'Staff')

            if not name or not username or not password:
                flash('Please fill in all required fields.', 'danger')
                return redirect(url_for('register'))

            if password != confirm_password:
                flash('Passwords do not match. Please verify your password.', 'danger')
                return redirect(url_for('register'))

            if User.query.filter_by(username=username).first():
                flash(f'Username "{username}" is already registered.', 'warning')
                return redirect(url_for('register'))

            if email and User.query.filter_by(email=email).first():
                flash(f'Email address "{email}" is already associated with an account.', 'warning')
                return redirect(url_for('register'))

            user = User(
                username=username,
                name=name,
                email=email if email else None,
                role=role if role in ['Admin', 'Staff'] else 'Staff',
                is_active=True
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            flash('Account created successfully! Please sign in with your credentials.', 'success')
            return redirect(url_for('login'))

        return render_template('register.html')


    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('You have been logged out successfully.', 'info')
        return redirect(url_for('login'))

    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        if request.method == 'POST':
            current_user.name = request.form.get('name', '').strip()
            current_user.email = request.form.get('email', '').strip()
            new_password = request.form.get('new_password', '').strip()
            if new_password:
                current_user.set_password(new_password)
                flash('Password updated successfully.', 'success')
            db.session.commit()
            flash('Profile details updated.', 'success')
            return redirect(url_for('profile'))
        return render_template('profile.html')

    @app.route('/users', methods=['GET', 'POST'])
    @login_required
    @admin_required
    def users_list():
        users = User.query.order_by(User.id.desc()).all()
        return render_template('users/list.html', users=users)

    @app.route('/users/create', methods=['POST'])
    @login_required
    @admin_required
    def user_create():
        username = request.form.get('username', '').strip()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'Staff')

        if User.query.filter_by(username=username).first():
            flash(f'Username "{username}" is already taken.', 'danger')
            return redirect(url_for('users_list'))

        user = User(username=username, name=name, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f'User account {username} ({role}) created successfully.', 'success')
        return redirect(url_for('users_list'))
    
    @app.route('/users/delete/<int:user_id>', methods=['POST'])
    @login_required
    def user_delete(user_id):
        # Only admins can delete accounts
        if current_user.role != 'Admin':
            abort(403)

        # Prevent deleting your own account
        if current_user.id == user_id:
            flash("You cannot delete your own account.", "danger")
            return redirect(url_for('users_list'))

        user = User.query.get_or_404(user_id)

        # Admins can delete Staff, but not other Admins
        if user.role == 'Admin':
            flash("You cannot delete another Admin account.", "danger")
            return redirect(url_for('users_list'))

        try:
            db.session.delete(user)
            db.session.commit()
            flash("Staff account deleted successfully.", "success")
        except Exception:
            db.session.rollback()
            flash(
                "Unable to delete this Staff account. It may be linked to other records.",
            "danger"
            )

        return redirect(url_for('users_list'))


    # ---------------------------------------------------------
    # DASHBOARD ROUTE
    # ---------------------------------------------------------
    @app.route('/about')
    @login_required
    def about_page():
        return render_template('about.html',
                               customer_count=Customer.query.count(),
                               frame_count=Frame.query.count(),
                               lens_count=Lens.query.count(),
                               bill_count=Invoice.query.count(),
                               app_name=APP_NAME,
                               app_tagline=APP_TAGLINE,
                               developer_name=DEVELOPER_NAME,
                               developer_contact=DEVELOPER_CONTACT,
                               run_count=get_run_count(),
                               license_status=get_license_status(),
                               current_year=datetime.utcnow().year)

    @app.route('/')
    @app.route('/dashboard')
    @login_required
    def dashboard():
        total_customers = Customer.query.count()
        
        today = datetime.utcnow().date()
        todays_sales = db.session.query(func.sum(Invoice.paid_amount)).filter(
            func.date(Invoice.invoice_date) == today
        ).scalar() or 0.0

        total_frames = Frame.query.count()
        total_lenses = Lens.query.count()
        total_products = total_frames + total_lenses

        low_stock_frames = Frame.query.filter(Frame.quantity <= Frame.min_stock).count()
        low_stock_lenses = Lens.query.filter(Lens.quantity <= Lens.min_stock).count()
        low_stock_count = low_stock_frames + low_stock_lenses

        recent_sales = Invoice.query.order_by(Invoice.id.desc()).limit(5).all()

        # Sales Trend Chart Data (Last 7 days)
        sales_dates = []
        sales_values = []
        for i in range(6, -1, -1):
            day_date = today - timedelta(days=i)
            day_str = day_date.strftime('%b %d')
            val = db.session.query(func.sum(Invoice.total_amount)).filter(
                func.date(Invoice.invoice_date) == day_date
            ).scalar() or 0.0
            sales_dates.append(day_str)
            sales_values.append(round(val, 2))

        return render_template(
            'dashboard.html',
            total_customers=total_customers,
            todays_sales=todays_sales,
            total_products=total_products,
            total_frames=total_frames,
            total_lenses=total_lenses,
            low_stock_count=low_stock_count,
            recent_invoices=recent_sales,
            sales_dates=sales_dates,
            sales_values=sales_values
        )

    # ---------------------------------------------------------
    # CUSTOMER MANAGEMENT
    # ---------------------------------------------------------
    @app.route('/customers')
    @login_required
    def customers_list():
        search = request.args.get('search', '').strip()
        query = Customer.query
        if search:
            query = query.filter(or_(Customer.name.ilike(f'%{search}%'), Customer.phone.ilike(f'%{search}%'), Customer.customer_code.ilike(f'%{search}%')))
        customers = query.order_by(Customer.id.desc()).all()
        return render_template('customers/list.html', customers=customers, search=search)

    @app.route('/customers/create', methods=['GET', 'POST'])
    @login_required
    def customer_create():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            phone = request.form.get('phone', '').strip()
            email = request.form.get('email', '').strip()
            dob_str = request.form.get('dob', '').strip()
            gender = request.form.get('gender', 'Unspecified')
            address = request.form.get('address', '').strip()
            notes = request.form.get('notes', '').strip()

            dob = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None

            customer_code = generate_customer_code()
            customer = Customer(
                customer_code=customer_code,
                name=name,
                phone=phone,
                email=email if email else None,
                dob=dob,
                gender=gender,
                address=address if address else None,
                notes=notes if notes else None
            )
            db.session.add(customer)
            db.session.commit()
            flash(f'Customer {name} created successfully (Code: {customer_code}).', 'success')
            return redirect(url_for('customer_view', customer_id=customer.id))

        return render_template('customers/form.html', customer=None)

    @app.route('/customers/<int:customer_id>')
    @login_required
    def customer_view(customer_id):
        customer = Customer.query.get_or_404(customer_id)
        prescriptions = customer.prescriptions.order_by(Prescription.id.desc()).all()
        orders = customer.orders.order_by(Order.id.desc()).all()
        invoices = customer.invoices.order_by(Invoice.id.desc()).all()
        payments = customer.payments.order_by(Payment.id.desc()).all()
        return render_template(
            'customers/view.html',
            customer=customer,
            prescriptions=prescriptions,
            orders=orders,
            invoices=invoices,
            payments=payments
        )

    @app.route('/customers/<int:customer_id>/edit', methods=['GET', 'POST'])
    @login_required
    def customer_edit(customer_id):
        customer = Customer.query.get_or_404(customer_id)
        if request.method == 'POST':
            customer.name = request.form.get('name', '').strip()
            customer.phone = request.form.get('phone', '').strip()
            customer.email = request.form.get('email', '').strip() or None
            dob_str = request.form.get('dob', '').strip()
            customer.dob = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None
            customer.gender = request.form.get('gender', 'Unspecified')
            customer.address = request.form.get('address', '').strip() or None
            customer.notes = request.form.get('notes', '').strip() or None

            db.session.commit()
            flash(f'Customer {customer.name} updated successfully.', 'success')
            return redirect(url_for('customer_view', customer_id=customer.id))

        return render_template('customers/form.html', customer=customer)

    @app.route('/customers/<int:customer_id>/delete', methods=['POST'])
    @login_required
    def customer_delete(customer_id):
        customer = Customer.query.get_or_404(customer_id)
        name = customer.name
        db.session.delete(customer)
        db.session.commit()
        flash(f'Customer {name} deleted.', 'info')
        return redirect(url_for('customers_list'))

    # ---------------------------------------------------------
    # EYE TEST / PRESCRIPTION MANAGEMENT
    # ---------------------------------------------------------
    @app.route('/prescriptions')
    @login_required
    def prescriptions_list():
        prescriptions = Prescription.query.order_by(Prescription.id.desc()).all()
        return render_template('prescriptions/list.html', prescriptions=prescriptions)

    @app.route('/prescriptions/create', methods=['GET', 'POST'])
    @login_required
    def prescription_create():
        if request.method == 'POST':
            customer_id = request.form.get('customer_id', type=int)
            prescription_date_str = request.form.get('prescription_date', '').strip()
            next_test_date_str = request.form.get('next_test_date', '').strip()

            rx = Prescription(
                customer_id=customer_id,
                spherical_od=request.form.get('spherical_od', '0.00'),
                cyl_od=request.form.get('cyl_od', '0.00'),
                axis_od=request.form.get('axis_od', '0'),
                add_od=request.form.get('add_od', '0.00'),
                spherical_os=request.form.get('spherical_os', '0.00'),
                cyl_os=request.form.get('cyl_os', '0.00'),
                axis_os=request.form.get('axis_os', '0'),
                add_os=request.form.get('add_os', '0.00'),
                pd=request.form.get('pd', ''),
                near_pd=request.form.get('near_pd', ''),
                doctor_name=request.form.get('doctor_name', ''),
                prescription_date=datetime.strptime(prescription_date_str, '%Y-%m-%d').date() if prescription_date_str else datetime.utcnow().date(),
                next_test_date=datetime.strptime(next_test_date_str, '%Y-%m-%d').date() if next_test_date_str else None,
                notes=request.form.get('notes', '')
            )
            db.session.add(rx)
            db.session.commit()
            flash('Eye prescription recorded successfully.', 'success')
            return redirect(url_for('customer_view', customer_id=customer_id))

        customers = Customer.query.order_by(Customer.name).all()
        selected_customer_id = request.args.get('customer_id', type=int)
        today_date = datetime.utcnow().date().strftime('%Y-%m-%d')
        next_year_date = (datetime.utcnow().date() + timedelta(days=365)).strftime('%Y-%m-%d')
        return render_template('prescriptions/form.html', customers=customers, selected_customer_id=selected_customer_id, today_date=today_date, next_year_date=next_year_date)

    @app.route('/prescriptions/<int:rx_id>')
    @login_required
    def prescription_view(rx_id):
        rx = Prescription.query.get_or_404(rx_id)
        return render_template('prescriptions/view.html', rx=rx)

    @app.route('/prescriptions/<int:rx_id>/delete', methods=['POST'])
    @login_required
    def prescription_delete(rx_id):
        rx = Prescription.query.get_or_404(rx_id)
        cust_id = rx.customer_id
        db.session.delete(rx)
        db.session.commit()
        flash('Prescription deleted.', 'info')
        return redirect(url_for('customer_view', customer_id=cust_id))

    # ---------------------------------------------------------
    # FRAME MANAGEMENT
    # ---------------------------------------------------------
    
    # @app.route('/frames')
    # @login_required
    # def frames_list():
    #     gender = request.args.get('gender', '').strip()
    #     supplier_name = request.args.get('supplier_name', '').strip()

    #     query = Frame.query

    #     if gender:
    #         query = query.filter_by(gender=gender)

    #     if supplier_name:
    #         query = query.filter_by(supplier_id=supplier_name)

    #     frames = query.order_by(Frame.id.desc()).all()
    #     suppliers = Supplier.query.order_by(Supplier.name).all()

    #     return render_template(
    #         'frames/list.html',
    #         frames=frames,
    #         suppliers=suppliers,
    #     selected_gender=gender,
    #     selected_supplier=supplier_name
    #  )


    # @app.route('/frames/create', methods=['GET', 'POST'])
    # @login_required
    # def frame_create():
    #     if request.method == 'POST':
    #         brand = request.form.get('brand', '').strip()
    #         model = request.form.get('model', '').strip()
    #         gender = request.form.get('gender', 'Unisex')
    #         frame_type = request.form.get('frame_type', 'Full Rim')
    #         material = request.form.get('material', '')
    #         color = request.form.get('color', '')
    #         size = request.form.get('size', '')
    #         purchase_price = float(request.form.get('purchase_price', 0.0))
    #         selling_price = float(request.form.get('selling_price', 0.0))
    #         quantity = int(request.form.get('quantity', 0))
    #         min_stock = int(request.form.get('min_stock', 3))
    #         supplier_id = request.form.get('supplier_id', '').strip()

    #         image_file = request.files.get('image')
    #         image_filename = save_uploaded_file(image_file, app.config['UPLOAD_FOLDER']) if image_file else None

    #         frame_code = generate_frame_code()
    #         frame = Frame(
    #             frame_code=frame_code,
    #             brand=brand,
    #             model=model,
    #             gender=gender,
    #             frame_type=frame_type,
    #             material=material,
    #             color=color,
    #             size=size,
    #             purchase_price=purchase_price,
    #             selling_price=selling_price,
    #             quantity=quantity,
    #             min_stock=min_stock,
    #             supplier_id=supplier_id if supplier_id else None,
    #             image_filename=image_filename,
    #             status='In Stock' if quantity > 0 else 'Out of Stock'
    #         )
    #         db.session.add(frame)
    #         db.session.commit()

    #         # Record initial inventory transaction
    #         if quantity > 0:
    #             txn = InventoryTransaction(
    #                 item_type='Frame',
    #                 item_id=frame.id,
    #                 item_name=f"{brand} {model}",
    #                 transaction_type='Stock In',
    #                 quantity=quantity,
    #                 reference='Initial Stock',
    #                 notes='New frame inventory entry'
    #             )
    #             db.session.add(txn)
    #             db.session.commit()

    #         flash(f'Optical frame {brand} {model} added to inventory.', 'success')
    #         return redirect(url_for('frames_list'))

    #     suppliers = Supplier.query.order_by(Supplier.name).all()
    #     return render_template('frames/form.html', frame=None, suppliers=suppliers)

    # @app.route('/frames/<int:frame_id>/edit', methods=['GET', 'POST'])
    # @login_required
    # def frame_edit(frame_id):
    #     frame = Frame.query.get_or_404(frame_id)
    #     if request.method == 'POST':
    #         frame.brand = request.form.get('brand', '').strip()
    #         frame.model = request.form.get('model', '').strip()
    #         frame.gender = request.form.get('gender', 'Unisex')
    #         frame.frame_type = request.form.get('frame_type', 'Full Rim')
    #         frame.material = request.form.get('material', '')
    #         frame.color = request.form.get('color', '')
    #         frame.size = request.form.get('size', '')
    #         frame.purchase_price = float(request.form.get('purchase_price', 0.0))
    #         frame.selling_price = float(request.form.get('selling_price', 0.0))
    #         frame.quantity = int(request.form.get('quantity', 0))
    #         frame.min_stock = int(request.form.get('min_stock', 3))
    #         supplier_id = request.form.get('supplier_id', '').strip()
    #         frame.supplier_id = supplier_id or None 
    #         frame.status = 'In Stock' if frame.quantity > 0 else 'Out of Stock'

    #         image_file = request.files.get('image')
    #         if image_file and image_file.filename != '':
    #             frame.image_filename = save_uploaded_file(image_file, app.config['UPLOAD_FOLDER'])

    #         db.session.commit()
    #         flash(f'Frame {frame.brand} {frame.model} updated.', 'success')
    #         return redirect(url_for('frames_list'))

    #     suppliers = Supplier.query.order_by(Supplier.name).all()
    #     return render_template('frames/form.html', frame=frame, suppliers=suppliers)

    # @app.route('/frames/<int:frame_id>/delete', methods=['POST'])
    # @login_required
    # def frame_delete(frame_id):
    #     frame = Frame.query.get_or_404(frame_id)
    #     brand = frame.brand
    #     model = frame.model
    #     db.session.delete(frame)
    #     db.session.commit()
    #     flash(f'Frame {brand} {model} deleted.', 'info')
    #     return redirect(url_for('frames_list'))
    
    
    @app.route('/frames')
    @login_required
    def frames_list():
        gender = request.args.get('gender', '').strip()
        supplier_name = request.args.get('supplier_name', '').strip()

        query = Frame.query

        if gender:
            query = query.filter_by(gender=gender)

        if supplier_name:
            try:
                supplier_id = int(supplier_name)
                query = query.filter_by(supplier_id=supplier_id)
            except ValueError:
                pass

        frames = query.order_by(Frame.id.desc()).all()
        suppliers = Supplier.query.order_by(Supplier.name).all()

        return render_template(
            'frames/list.html',
            frames=frames,
            suppliers=suppliers,
            selected_gender=gender,
            selected_supplier=supplier_name
        )

    @app.route('/frames/create', methods=['GET', 'POST'])
    @login_required
    def frame_create():
        if request.method == 'POST':
            try:
                brand = request.form.get('brand', '').strip()
                model = request.form.get('model', '').strip()

                if not brand or not model:
                    flash('Brand and model are required.', 'danger')
                    return redirect(url_for('frame_create'))

                gender = request.form.get('gender', 'Unisex')
                frame_type = request.form.get('frame_type', 'Full Rim')
                material = request.form.get('material', '').strip()
                color = request.form.get('color', '').strip()
                size = request.form.get('size', '').strip()

                purchase_price = float(
                    request.form.get('purchase_price') or 0
                )
                selling_price = float(
                    request.form.get('selling_price') or 0
                )
                quantity = int(request.form.get('quantity') or 0)
                min_stock = int(request.form.get('min_stock') or 3)

                supplier_value = request.form.get(
                    'supplier_id', ''
                ).strip()
                supplier_id = int(supplier_value) if supplier_value else None

                image_file = request.files.get('image')
                image_filename = None

                if image_file and image_file.filename:
                    image_filename = save_uploaded_file(
                        image_file, app.config['UPLOAD_FOLDER']
                    )

                frame = Frame(
                    frame_code=generate_frame_code(),
                    brand=brand,
                    model=model,
                    gender=gender,
                    frame_type=frame_type,
                    material=material,
                    color=color,
                    size=size,
                    purchase_price=purchase_price,
                    selling_price=selling_price,
                    quantity=quantity,
                    min_stock=min_stock,
                    supplier_id=supplier_id,
                    image_filename=image_filename,
                    status='In Stock' if quantity > 0 else 'Out of Stock'
                )

                db.session.add(frame)
                db.session.flush()

                if quantity > 0:
                    txn = InventoryTransaction(
                        item_type='Frame',
                        item_id=frame.id,
                        item_name=f'{brand} {model}',
                        transaction_type='Stock In',
                        quantity=quantity,
                        reference='Initial Stock',
                        notes='New frame inventory entry'
                    )
                    db.session.add(txn)

                db.session.commit()

                flash(
                    f'Frame {brand} {model} saved successfully.',
                    'success'
                )
                return redirect(url_for('frames_list'))

            except (ValueError, TypeError):
                db.session.rollback()
                flash(
                    'Enter valid prices, quantity, and supplier details.',
                    'danger'
                )
                return redirect(url_for('frame_create'))

            except Exception:
                db.session.rollback()
                app.logger.exception('Failed to save optical frame')
                flash(
                    'Frame could not be saved. Check the terminal for '
                    'the database error.',
                    'danger'
                )
                return redirect(url_for('frame_create'))

        suppliers = Supplier.query.order_by(Supplier.name).all()
        return render_template(
            'frames/form.html',
            frame=None,
            suppliers=suppliers
        )

    @app.route('/frames/<int:frame_id>/edit', methods=['GET', 'POST'])
    @login_required
    def frame_edit(frame_id):
        frame = Frame.query.get_or_404(frame_id)

        if request.method == 'POST':
            try:
                brand = request.form.get('brand', '').strip()
                model = request.form.get('model', '').strip()

                if not brand or not model:
                    flash('Brand and model are required.', 'danger')
                    return redirect(
                        url_for('frame_edit', frame_id=frame.id)
                    )

                frame.brand = brand
                frame.model = model
                frame.gender = request.form.get('gender', 'Unisex')
                frame.frame_type = request.form.get(
                    'frame_type', 'Full Rim'
                )
                frame.material = request.form.get('material', '').strip()
                frame.color = request.form.get('color', '').strip()
                frame.size = request.form.get('size', '').strip()
                frame.purchase_price = float(
                    request.form.get('purchase_price') or 0
                )
                frame.selling_price = float(
                    request.form.get('selling_price') or 0
                )
                frame.quantity = int(request.form.get('quantity') or 0)
                frame.min_stock = int(request.form.get('min_stock') or 3)

                supplier_value = request.form.get(
                    'supplier_id', ''
                ).strip()
                frame.supplier_id = (
                    int(supplier_value) if supplier_value else None
                )

                frame.status = (
                    'In Stock' if frame.quantity > 0 else 'Out of Stock'
                )

                image_file = request.files.get('image')
                if image_file and image_file.filename:
                    frame.image_filename = save_uploaded_file(
                        image_file, app.config['UPLOAD_FOLDER']
                    )

                db.session.commit()
                flash(
                    f'Frame {frame.brand} {frame.model} updated.',
                    'success'
                )
                return redirect(url_for('frames_list'))

            except (ValueError, TypeError):
                db.session.rollback()
                flash('Enter valid numeric values.', 'danger')
                return redirect(
                    url_for('frame_edit', frame_id=frame.id)
                )

            except Exception:
                db.session.rollback()
                app.logger.exception('Failed to update optical frame')
                flash('Frame could not be updated. Check the terminal.', 'danger')
                return redirect(
                    url_for('frame_edit', frame_id=frame.id)
                )

        suppliers = Supplier.query.order_by(Supplier.name).all()
        return render_template(
            'frames/form.html',
            frame=frame,
            suppliers=suppliers
        )

    @app.route('/frames/<int:frame_id>/delete', methods=['POST'])
    @login_required
    def frame_delete(frame_id):
        frame = Frame.query.get_or_404(frame_id)

        try:
            brand = frame.brand
            model = frame.model

            db.session.delete(frame)
            db.session.commit()

            flash(f'Frame {brand} {model} deleted.', 'success')

        except Exception:
            db.session.rollback()
            app.logger.exception('Failed to delete optical frame')
            flash(
                'Frame could not be deleted. It may be linked to other records.',
                'danger'
            )

        return redirect(url_for('frames_list'))

    # ---------------------------------------------------------
    # LENS MANAGEMENT
    # ---------------------------------------------------------
    
    @app.route('/lenses')
    @login_required
    def lenses_list():
     lens_type = request.args.get('lens_type', '').strip()
     supplier_name = request.args.get('supplier_name', '').strip()

     query = Lens.query

     if lens_type:
        query = query.filter_by(lens_type=lens_type)

     if supplier_name:
        query = query.filter_by(supplier_id=supplier_name)

     lenses = query.order_by(Lens.id.desc()).all()
     suppliers = Supplier.query.order_by(Supplier.name).all()

     return render_template(
        'lenses/list.html',
        lenses=lenses,
        suppliers=suppliers,
        selected_type=lens_type,
        selected_supplier=supplier_name
     )


    @app.route('/lenses/create', methods=['GET', 'POST'])
    @login_required
    def lens_create():
        if request.method == 'POST':
            brand = request.form.get('brand', '').strip()
            lens_type = request.form.get('lens_type', 'Single Vision')
            material = request.form.get('material', '')
            index_val = request.form.get('index_val', '1.56')
            coating = request.form.get('coating', '')
            purchase_price = float(request.form.get('purchase_price', 0.0))
            selling_price = float(request.form.get('selling_price', 0.0))
            quantity = int(request.form.get('quantity', 0))
            min_stock = int(request.form.get('min_stock', 5))
            supplier_id = request.form.get('supplier_id', '').strip()
            description = request.form.get('description', '')

            lens_code = generate_lens_code()
            lens = Lens(
                lens_code=lens_code,
                brand=brand,
                lens_type=lens_type,
                material=material,
                index_val=index_val,
                coating=coating,
                purchase_price=purchase_price,
                selling_price=selling_price,
                quantity=quantity,
                min_stock=min_stock,
                supplier_id=supplier_id if supplier_id else None,
                description=description
            )
            db.session.add(lens)
            db.session.commit()

            if quantity > 0:
                txn = InventoryTransaction(
                    item_type='Lens',
                    item_id=lens.id,
                    item_name=f"{brand} - {lens_type}",
                    transaction_type='Stock In',
                    quantity=quantity,
                    reference='Initial Stock',
                    notes='New lens inventory entry'
                )
                db.session.add(txn)
                db.session.commit()

            flash(f'Lens {brand} ({lens_type}) added to inventory.', 'success')
            return redirect(url_for('lenses_list'))

        suppliers = Supplier.query.order_by(Supplier.name).all()
        return render_template('lenses/form.html', lens=None, suppliers=suppliers)

    @app.route('/lenses/<int:lens_id>/edit', methods=['GET', 'POST'])
    @login_required
    def lens_edit(lens_id):
        lens = Lens.query.get_or_404(lens_id)
        if request.method == 'POST':
            lens.brand = request.form.get('brand', '').strip()
            lens.lens_type = request.form.get('lens_type', 'Single Vision')
            lens.material = request.form.get('material', '')
            lens.index_val = request.form.get('index_val', '1.56')
            lens.coating = request.form.get('coating', '')
            lens.purchase_price = float(request.form.get('purchase_price', 0.0))
            lens.selling_price = float(request.form.get('selling_price', 0.0))
            lens.quantity = int(request.form.get('quantity', 0))
            lens.min_stock = int(request.form.get('min_stock', 5))
            supplier_id = request.form.get('supplier_id', '').strip()
            lens.supplier_id = supplier_id or None
            lens.description = request.form.get('description', '')

            db.session.commit()
            flash(f'Lens {lens.brand} updated.', 'success')
            return redirect(url_for('lenses_list'))

        suppliers = Supplier.query.order_by(Supplier.name).all()
        return render_template('lenses/form.html', lens=lens, suppliers=suppliers)

    @app.route('/lenses/<int:lens_id>/delete', methods=['POST'])
    @login_required
    def lens_delete(lens_id):
        lens = Lens.query.get_or_404(lens_id)
        brand = lens.brand
        db.session.delete(lens)
        db.session.commit()
        flash(f'Lens {brand} deleted.', 'info')
        return redirect(url_for('lenses_list'))

    # ---------------------------------------------------------
    # ORDER MANAGEMENT
    # ---------------------------------------------------------
    @app.route('/orders')
    @login_required
    def orders_list():
        status = request.args.get('status', '').strip()
        query = Order.query
        if status:
            query = query.filter_by(status=status)
        orders = query.order_by(Order.id.desc()).all()
        return render_template('orders/list.html', orders=orders, selected_status=status)

    @app.route('/orders/create', methods=['GET', 'POST'])
    @login_required
    def order_create():
        if request.method == 'POST':
            customer_id = request.form.get('customer_id', type=int)
            prescription_id = request.form.get('prescription_id', type=int)
            frame_id = request.form.get('frame_id', type=int)
            lens_id = request.form.get('lens_id', type=int)
            quantity = int(request.form.get('quantity', 1))
            lens_details = request.form.get('lens_details', '').strip()

            other_charges = float(request.form.get('other_charges', 0.0))
            discount = float(request.form.get('discount', 0.0))
            advance_payment = float(request.form.get('advance_payment', 0.0))
            expected_delivery_date_str = request.form.get('expected_delivery_date', '').strip()
            status = request.form.get('status', 'New')
            notes = request.form.get('notes', '').strip()

            frame = Frame.query.get(frame_id) if frame_id else None
            lens = Lens.query.get(lens_id) if lens_id else None

            # Calculate total amount
            frame_price = frame.selling_price if frame else 0.0
            lens_price = (lens.selling_price * quantity) if lens else 0.0
            total_amount = frame_price + lens_price + other_charges - discount
            if total_amount < 0:
                total_amount = 0.0

            balance_amount = total_amount - advance_payment
            if balance_amount < 0:
                balance_amount = 0.0

            order_number = generate_order_number()
            order = Order(
                order_number=order_number,
                customer_id=customer_id,
                prescription_id=prescription_id if prescription_id else None,
                frame_id=frame_id if frame_id else None,
                lens_id=lens_id if lens_id else None,
                quantity=quantity,
                lens_details=lens_details,
                total_amount=total_amount,
                discount=discount,
                advance_payment=advance_payment,
                balance_amount=balance_amount,
                order_date=datetime.utcnow().date(),
                expected_delivery_date=datetime.strptime(expected_delivery_date_str, '%Y-%m-%d').date() if expected_delivery_date_str else None,
                status=status,
                notes=notes
            )
            db.session.add(order)
            db.session.commit()

            # Automatically update stock quantities and log inventory transactions
            if frame and frame.quantity >= 1:
                frame.quantity -= 1
                if frame.quantity == 0:
                    frame.status = 'Out of Stock'
                txn_frame = InventoryTransaction(
                    item_type='Frame',
                    item_id=frame.id,
                    item_name=f"{frame.brand} {frame.model}",
                    transaction_type='Stock Out',
                    quantity=1,
                    reference=f"Order #{order_number}",
                    notes='Automated deduction on order placement'
                )
                db.session.add(txn_frame)

            if lens and lens.quantity >= quantity:
                lens.quantity -= quantity
                txn_lens = InventoryTransaction(
                    item_type='Lens',
                    item_id=lens.id,
                    item_name=f"{lens.brand} - {lens.lens_type}",
                    transaction_type='Stock Out',
                    quantity=quantity,
                    reference=f"Order #{order_number}",
                    notes='Automated deduction on order placement'
                )
                db.session.add(txn_lens)

            db.session.commit()
            flash(f'Optical order #{order_number} created successfully.', 'success')
            return redirect(url_for('invoice_create', order_id=order.id))

        customers = Customer.query.order_by(Customer.name).all()
        selected_customer_id = request.args.get('customer_id', type=int)
        selected_rx_id = request.args.get('rx_id', type=int)

        prescriptions = Prescription.query.filter_by(customer_id=selected_customer_id).all() if selected_customer_id else Prescription.query.all()
        frames = Frame.query.filter(Frame.quantity > 0).all()
        lenses = Lens.query.filter(Lens.quantity > 0).all()
        default_delivery_date = (datetime.utcnow().date() + timedelta(days=5)).strftime('%Y-%m-%d')

        return render_template(
            'orders/form.html',
            customers=customers,
            prescriptions=prescriptions,
            frames=frames,
            lenses=lenses,
            selected_customer_id=selected_customer_id,
            selected_rx_id=selected_rx_id,
            default_delivery_date=default_delivery_date
        )

    @app.route('/orders/<int:order_id>')
    @login_required
    def order_view(order_id):
        order = Order.query.get_or_404(order_id)
        if order.invoice:
            return redirect(url_for('invoice_view', invoice_id=order.invoice.id))
        return redirect(url_for('invoice_create', order_id=order.id))

    @app.route('/orders/<int:order_id>/status', methods=['POST'])
    @login_required
    def order_update_status(order_id):
        order = Order.query.get_or_404(order_id)
        new_status = request.form.get('status', 'Processing')
        order.status = new_status
        db.session.commit()
        flash(f'Order #{order.order_number} status updated to "{new_status}".', 'success')
        return redirect(url_for('orders_list'))

    @app.route('/orders/track')
    @login_required
    def order_track():
        query = request.args.get('query', '').strip()
        matched_orders = []
        searched = False
        if query:
            searched = True
            matched_orders = Order.query.join(Customer).filter(
                or_(
                    Order.order_number.ilike(f'%{query}%'),
                    Customer.phone.ilike(f'%{query}%'),
                    Customer.name.ilike(f'%{query}%')
                )
            ).order_by(Order.id.desc()).all()

        return render_template('orders/track.html', query=query, matched_orders=matched_orders, searched=searched)

    # ---------------------------------------------------------
    # BILLING & INVOICE MANAGEMENT
    # ---------------------------------------------------------
    @app.route('/billing')
    @login_required
    def billing_list():
        invoices = Invoice.query.order_by(Invoice.id.desc()).all()
        item_counts = dict(db.session.query(InvoiceItem.invoice_id, func.count(InvoiceItem.id)).group_by(InvoiceItem.invoice_id).all())
        return render_template('billing/list.html', invoices=invoices, item_counts=item_counts)

    @app.route('/billing/generate', methods=['GET', 'POST'])
    @login_required
    def invoice_create_direct():
        if request.method == 'POST':
            customer = Customer.query.get_or_404(request.form.get('customer_id', type=int))
            back = redirect(url_for('invoice_create_direct', customer_id=customer.id))
            try:
                cart = json.loads(request.form.get('items_json') or '[]')
                discount = max(float(request.form.get('discount') or 0), 0.0)
                tax_rate = max(float(request.form.get('tax_rate') or 0), 0.0)
                lines, used = [], {}
                for row in cart:
                    qty = max(int(row.get('qty') or 1), 1)
                    kind = row.get('type')
                    if kind in ('Frame', 'Lens'):
                        product = (Frame if kind == 'Frame' else Lens).query.get(int(row.get('id') or 0))
                        if not product:
                            continue
                        used[(kind, product.id)] = used.get((kind, product.id), 0) + qty
                        if used[(kind, product.id)] > product.quantity:
                            flash(f'Not enough stock for {kind.lower()} "{product.brand}" (only {product.quantity} left).', 'danger')
                            return back
                        name = f"{product.brand} {product.model}" if kind == 'Frame' else f"{product.brand} - {product.lens_type}"
                        lines.append(dict(type=kind, product=product, description=name, quantity=qty, unit_price=product.selling_price))
                    else:
                        name = (row.get('name') or '').strip()
                        price = float(row.get('price') or 0)
                        if name and price >= 0:
                            lines.append(dict(type='Custom', product=None, description=name[:255], quantity=qty, unit_price=price))
            except (ValueError, TypeError, AttributeError):
                flash('The bill contained invalid values. Please check the items and try again.', 'danger')
                return back
            if not lines:
                flash('Add at least one item to generate a bill.', 'warning')
                return back

            def amount_of(kind):
                return round(sum(l['quantity'] * l['unit_price'] for l in lines if l['type'] == kind), 2)

            payment_method = request.form.get('payment_method', 'Cash')
            invoice_number = generate_invoice_number()
            invoice = Invoice(
                invoice_number=invoice_number,
                order_id=None,
                customer_id=customer.id,
                invoice_date=datetime.utcnow().date(),
                frame_amount=amount_of('Frame'),
                lens_amount=amount_of('Lens'),
                other_charges=amount_of('Custom'),
                discount=discount,
                tax_rate=tax_rate,
                paid_amount=0.0,
                payment_method=payment_method,
                notes=request.form.get('notes', '').strip()
            )
            invoice.calculate_totals()
            invoice.paid_amount = invoice.total_amount   # a bill is settled when it is generated
            invoice.calculate_totals()
            db.session.add(invoice)
            db.session.flush()

            for l in lines:
                p = l['product']
                db.session.add(InvoiceItem(invoice_id=invoice.id, item_type=l['type'], item_id=p.id if p else None,
                                           description=l['description'], quantity=l['quantity'], unit_price=l['unit_price']))
                if p:
                    p.quantity -= l['quantity']
                    if l['type'] == 'Frame' and p.quantity == 0:
                        p.status = 'Out of Stock'
                    db.session.add(InventoryTransaction(
                        item_type=l['type'], item_id=p.id, item_name=l['description'],
                        transaction_type='Stock Out', quantity=l['quantity'],
                        reference=f"Bill #{invoice_number}", notes='Automated deduction on bill generation'))

            if invoice.total_amount > 0:
                db.session.add(Payment(invoice_id=invoice.id, customer_id=customer.id, amount_paid=invoice.total_amount,
                                       payment_date=datetime.utcnow().date(), payment_method=payment_method,
                                       notes='Paid in full at billing'))
            db.session.commit()
            flash(f'Bill #{invoice_number} generated for {customer.name}.', 'success')
            return redirect(url_for('invoice_view', invoice_id=invoice.id))

        products = [dict(type='Frame', id=f.id, name=f"{f.brand} {f.model}", sub=f"{f.frame_type or ''} {f.color or ''}".strip() or 'Frame',
                         price=f.selling_price, stock=f.quantity) for f in Frame.query.filter(Frame.quantity > 0).all()]
        products += [dict(type='Lens', id=l.id, name=f"{l.brand} - {l.lens_type}", sub=f"Index {l.index_val or '-'}",
                          price=l.selling_price, stock=l.quantity) for l in Lens.query.filter(Lens.quantity > 0).all()]
        return render_template('billing/create_direct.html',
                               customers=Customer.query.order_by(Customer.name).all(),
                               products=products,
                               selected_customer_id=request.args.get('customer_id', type=int))

    @app.route('/billing/create/<int:order_id>', methods=['GET', 'POST'])
    @login_required
    def invoice_create(order_id):
        order = Order.query.get_or_404(order_id)
        if order.invoice:
            flash(f'Invoice already exists for order #{order.order_number}.', 'info')
            return redirect(url_for('invoice_view', invoice_id=order.invoice.id))

        frame_amount = order.frame.selling_price if order.frame else 0.0
        lens_amount = (order.lens.selling_price * order.quantity) if order.lens else 0.0

        if request.method == 'POST':
            other_charges = float(request.form.get('other_charges', 0.0))
            discount = float(request.form.get('discount', 0.0))
            tax_rate = float(request.form.get('tax_rate', 0.0))
            paid_amount = float(request.form.get('paid_amount', 0.0))
            payment_method = request.form.get('payment_method', 'Cash')
            notes = request.form.get('notes', '').strip()

            invoice_number = generate_invoice_number()
            invoice = Invoice(
                invoice_number=invoice_number,
                order_id=order.id,
                customer_id=order.customer_id,
                invoice_date=datetime.utcnow().date(),
                frame_amount=frame_amount,
                lens_amount=lens_amount,
                other_charges=other_charges,
                discount=discount,
                tax_rate=tax_rate,
                paid_amount=paid_amount,
                payment_method=payment_method,
                notes=notes
            )
            invoice.calculate_totals()
            db.session.add(invoice)
            db.session.commit()

            # Record payment entry if paid_amount > 0
            if paid_amount > 0:
                payment = Payment(
                    invoice_id=invoice.id,
                    customer_id=order.customer_id,
                    amount_paid=paid_amount,
                    payment_date=datetime.utcnow().date(),
                    payment_method=payment_method,
                    notes='Initial invoice deposit / payment'
                )
                db.session.add(payment)
                db.session.commit()

            flash(f'Invoice #{invoice_number} issued successfully.', 'success')
            return redirect(url_for('invoice_view', invoice_id=invoice.id))

        return render_template('billing/create.html', order=order, frame_amount=frame_amount, lens_amount=lens_amount)

    @app.route('/billing/<int:invoice_id>')
    @login_required
    def invoice_view(invoice_id):
        invoice = Invoice.query.get_or_404(invoice_id)
        return render_template('billing/view.html', invoice=invoice, items=get_bill_items(invoice))

    @app.route('/billing/<int:invoice_id>/pdf')
    @login_required
    def invoice_pdf(invoice_id):
        invoice = Invoice.query.get_or_404(invoice_id)
        pdf_data = generate_bill_pdf(invoice, get_bill_items(invoice), app.config)
        response = make_response(pdf_data)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename=Invoice_{invoice.invoice_number}.pdf'
        return response

    # ---------------------------------------------------------
    # INVENTORY AUDIT & ADJUSTMENTS
    # ---------------------------------------------------------
    @app.route('/inventory')
    @login_required
    def inventory_list():
        low_stock_frames = Frame.query.filter(Frame.quantity <= Frame.min_stock).all()
        low_stock_lenses = Lens.query.filter(Lens.quantity <= Lens.min_stock).all()

        low_stock_items = []
        for f in low_stock_frames:
            low_stock_items.append({
                'item_type': 'Frame',
                'id': f.id,
                'code': f.frame_code,
                'name': f"{f.brand} {f.model}",
                'quantity': f.quantity,
                'min_stock': f.min_stock,
                'supplier': f.supplier.name if f.supplier else 'N/A'
            })
        for l in low_stock_lenses:
            low_stock_items.append({
                'item_type': 'Lens',
                'id': l.id,
                'code': l.lens_code,
                'name': f"{l.brand} - {l.lens_type}",
                'quantity': l.quantity,
                'min_stock': l.min_stock,
                'supplier': l.supplier.name if l.supplier else 'N/A'
            })

        transactions = InventoryTransaction.query.order_by(InventoryTransaction.id.desc()).limit(50).all()
        return render_template('inventory/list.html', low_stock_items=low_stock_items, transactions=transactions)

    @app.route('/inventory/adjust', methods=['GET', 'POST'])
    @login_required
    def inventory_adjust():
        if request.method == 'POST':
            item_type = request.form.get('item_type', 'Frame')
            transaction_type = request.form.get('transaction_type', 'Stock In')
            quantity = int(request.form.get('quantity', 1))
            reference = request.form.get('reference', '').strip()
            notes = request.form.get('notes', '').strip()

            if item_type == 'Frame':
                frame_id = request.form.get('frame_id', type=int)
                frame = Frame.query.get_or_404(frame_id)
                item_name = f"{frame.brand} {frame.model}"
                if transaction_type == 'Stock In':
                    frame.quantity += quantity
                elif transaction_type == 'Stock Out':
                    if frame.quantity < quantity:
                        flash(f'Cannot remove {quantity} frames. Current stock is only {frame.quantity}.', 'danger')
                        return redirect(url_for('inventory_adjust'))
                    frame.quantity -= quantity
                else: # Adjustment
                    frame.quantity = quantity

                frame.status = 'In Stock' if frame.quantity > 0 else 'Out of Stock'

            else: # Lens
                lens_id = request.form.get('lens_id', type=int)
                lens = Lens.query.get_or_404(lens_id)
                item_name = f"{lens.brand} - {lens.lens_type}"
                if transaction_type == 'Stock In':
                    lens.quantity += quantity
                elif transaction_type == 'Stock Out':
                    if lens.quantity < quantity:
                        flash(f'Cannot remove {quantity} lenses. Current stock is only {lens.quantity}.', 'danger')
                        return redirect(url_for('inventory_adjust'))
                    lens.quantity -= quantity
                else: # Adjustment
                    lens.quantity = quantity

            txn = InventoryTransaction(
                item_type=item_type,
                item_id=frame_id if item_type == 'Frame' else lens_id,
                item_name=item_name,
                transaction_type=transaction_type,
                quantity=quantity,
                reference=reference if reference else 'Manual Adjustment',
                notes=notes
            )
            db.session.add(txn)
            db.session.commit()
            flash(f'Inventory update recorded for {item_name}.', 'success')
            return redirect(url_for('inventory_list'))

        frames = Frame.query.order_by(Frame.brand).all()
        lenses = Lens.query.order_by(Lens.brand).all()
        selected_type = request.args.get('item_type', 'Frame')
        selected_id = request.args.get('item_id', type=int)

        return render_template('inventory/adjust.html', frames=frames, lenses=lenses, selected_type=selected_type, selected_id=selected_id)

    # ---------------------------------------------------------
    # SUPPLIER MANAGEMENT
    # ---------------------------------------------------------
    @app.route('/suppliers')
    @login_required
    def suppliers_list():
        suppliers = Supplier.query.order_by(Supplier.name).all()
        return render_template('suppliers/list.html', suppliers=suppliers)

    @app.route('/suppliers/create', methods=['GET', 'POST'])
    @login_required
    def supplier_create():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            contact_person = request.form.get('contact_person', '').strip()
            phone = request.form.get('phone', '').strip()
            email = request.form.get('email', '').strip()
            address = request.form.get('address', '').strip()
            products_supplied = request.form.get('products_supplied', '').strip()
            notes = request.form.get('notes', '').strip()

            supplier = Supplier(
                name=name,
                contact_person=contact_person if contact_person else None,
                phone=phone if phone else None,
                email=email if email else None,
                address=address if address else None,
                products_supplied=products_supplied if products_supplied else None,
                notes=notes if notes else None
            )
            db.session.add(supplier)
            db.session.commit()
            flash(f'Supplier {name} created successfully.', 'success')
            return redirect(url_for('suppliers_list'))

        return render_template('suppliers/form.html', supplier=None)

    @app.route('/suppliers/<int:supplier_id>/view')
    @login_required
    def supplier_view(supplier_id):
        supplier = Supplier.query.get_or_404(supplier_id)
        frames = supplier.frames.all()
        lenses = supplier.lenses.all()
        return render_template('suppliers/view.html', supplier=supplier, frames=frames, lenses=lenses)

    @app.route('/suppliers/<int:supplier_id>/edit', methods=['GET', 'POST'])
    @login_required
    def supplier_edit(supplier_id):
        supplier = Supplier.query.get_or_404(supplier_id)
        if request.method == 'POST':
            supplier.name = request.form.get('name', '').strip()
            supplier.contact_person = request.form.get('contact_person', '').strip() or None
            supplier.phone = request.form.get('phone', '').strip() or None
            supplier.email = request.form.get('email', '').strip() or None
            supplier.address = request.form.get('address', '').strip() or None
            supplier.products_supplied = request.form.get('products_supplied', '').strip() or None
            supplier.notes = request.form.get('notes', '').strip() or None

            db.session.commit()
            flash(f'Supplier {supplier.name} updated.', 'success')
            return redirect(url_for('suppliers_list'))

        return render_template('suppliers/form.html', supplier=supplier)

    @app.route('/suppliers/<int:supplier_id>/delete', methods=['POST'])
    @login_required
    def supplier_delete(supplier_id):
        supplier = Supplier.query.get_or_404(supplier_id)
        name = supplier.name
        db.session.delete(supplier)
        db.session.commit()
        flash(f'Supplier {name} deleted.', 'info')
        return redirect(url_for('suppliers_list'))

    # ---------------------------------------------------------
    # REPORTS & DATA EXPORT
    # ---------------------------------------------------------
    @app.route('/reports')
    @login_required
    @admin_required
    def reports_index():
        report_type = request.args.get('report_type', 'sales')
        start_date = request.args.get('start_date', (datetime.utcnow().date() - timedelta(days=30)).strftime('%Y-%m-%d'))
        end_date = request.args.get('end_date', datetime.utcnow().date().strftime('%Y-%m-%d'))

        headers, rows, title = _generate_report_data(report_type, start_date, end_date)

        return render_template(
            'reports/index.html',
            selected_report=report_type,
            start_date=start_date,
            end_date=end_date,
            report_headers=headers,
            report_rows=rows,
            report_title=title
        )

    @app.route('/reports/export/excel')
    @login_required
    @admin_required
    def report_export_excel():
        report_type = request.args.get('report_type', 'sales')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')

        headers, rows, title = _generate_report_data(report_type, start_date, end_date)
        excel_bytes = generate_report_excel(title, headers, rows)

        response = make_response(excel_bytes)
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = f'attachment; filename={report_type}_report.xlsx'
        return response

    @app.route('/reports/export/pdf')
    @login_required
    @admin_required
    def report_export_pdf():
        report_type = request.args.get('report_type', 'sales')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')

        headers, rows, title = _generate_report_data(report_type, start_date, end_date)
        pdf_bytes = generate_report_pdf(title, headers, rows)

        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'inline; filename={report_type}_report.pdf'
        return response

    def _generate_report_data(report_type, start_date_str, end_date_str):
        s_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else datetime.utcnow().date() - timedelta(days=30)
        e_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else datetime.utcnow().date()

        if report_type == 'sales':
            title = f"Sales & Invoices Report ({s_date} to {e_date})"
            headers = ["Invoice #", "Customer", "Date", "Total (INR)", "Paid (INR)", "Balance (INR)", "Payment Status"]
            invoices = Invoice.query.filter(func.date(Invoice.invoice_date) >= s_date, func.date(Invoice.invoice_date) <= e_date).all()
            rows = [
                [inv.invoice_number, inv.customer.name, inv.invoice_date.strftime('%Y-%m-%d'), f"INR {inv.total_amount:.2f}", f"INR {inv.paid_amount:.2f}", f"INR {inv.balance_amount:.2f}", inv.payment_status]
                for inv in invoices
            ]

        elif report_type == 'frame_stock':
            title = "Optical Frame Inventory Report"
            headers = ["Code", "Brand", "Model", "Gender", "Material", "Selling Price (INR)", "Quantity", "Supplier"]
            frames = Frame.query.order_by(Frame.brand).all()
            rows = [
                [f.frame_code, f.brand, f.model, f.gender, f.material or '-', f"INR {f.selling_price:.2f}", f.quantity, f.supplier.name if f.supplier else '-']
                for f in frames
            ]

        elif report_type == 'lens_stock':
            title = "Optical Lens Catalogue Report"
            headers = ["Code", "Brand", "Lens Type", "Index", "Coating", "Selling Price (INR)", "Quantity", "Supplier"]
            lenses = Lens.query.order_by(Lens.brand).all()
            rows = [
                [l.lens_code, l.brand, l.lens_type, l.index_val or '1.56', l.coating or '-', f"INR {l.selling_price:.2f}", l.quantity, l.supplier.name if l.supplier else '-']
                for l in lenses
            ]

        elif report_type == 'low_stock':
            title = "Low Stock Inventory Alert Report"
            headers = ["Category", "Code", "Item Name", "Current Qty", "Min Threshold", "Supplier"]
            frames = Frame.query.filter(Frame.quantity <= Frame.min_stock).all()
            lenses = Lens.query.filter(Lens.quantity <= Lens.min_stock).all()
            rows = []
            for f in frames:
                rows.append(["Frame", f.frame_code, f"{f.brand} {f.model}", f.quantity, f.min_stock, f.supplier.name if f.supplier else '-'])
            for l in lenses:
                rows.append(["Lens", l.lens_code, f"{l.brand} - {l.lens_type}", l.quantity, l.min_stock, l.supplier.name if l.supplier else '-'])

        elif report_type == 'pending_payments':
            title = "Pending & Outstanding Customer Payments"
            headers = ["Invoice #", "Customer Name", "Phone", "Invoice Date", "Total (INR)", "Paid (INR)", "Balance Due (INR)"]
            invoices = Invoice.query.filter(Invoice.balance_amount > 0).all()
            rows = [
                [inv.invoice_number, inv.customer.name, inv.customer.phone, inv.invoice_date.strftime('%Y-%m-%d'), f"INR {inv.total_amount:.2f}", f"INR {inv.paid_amount:.2f}", f"INR {inv.balance_amount:.2f}"]
                for inv in invoices
            ]

        elif report_type == 'profit':
            title = f"Sales Profit & Margin Summary ({s_date} to {e_date})"
            headers = ["Order #", "Customer", "Selling Total (INR)", "Est. Cost (INR)", "Gross Profit (INR)"]
            orders = Order.query.filter(func.date(Order.order_date) >= s_date, func.date(Order.order_date) <= e_date).all()
            rows = []
            for ord in orders:
                cost = (ord.frame.purchase_price if ord.frame else 0.0) + ((ord.lens.purchase_price * ord.quantity) if ord.lens else 0.0)
                profit = ord.total_amount - cost
                rows.append([ord.order_number, ord.customer.name, f"INR {ord.total_amount:.2f}", f"INR {cost:.2f}", f"INR {profit:.2f}"])

        else:
            headers, rows, title = [], [], "Empty Report"

        return headers, rows, title

    return app




    


import webview
import socket
import time
from threading import Thread

app = create_app()

class DesktopApi:
    """Exposed to the frontend as window.pywebview.api (see
    static/js/webview_exit.js, which calls exit_app() on the exit button).

    Deliberately holds NO reference to the pywebview Window object as an
    attribute -- some pywebview versions introspect every attribute of the
    exposed api instance (not just its methods) when wiring up the JS
    bridge, and a Window object can proxy into the underlying native
    WinForms handle. That handle contains self-referential .NET objects
    (Font.FontFamily.GenericSansSerif, AccessibleObject.SyncRoot), so
    naive attribute-walking recurses forever. exit_app() looks the window
    up from a plain module-level dict instead.
    """
    def exit_app(self):
        window = _windows.get('main')
        if window:
            window.destroy()

_windows = {}

from waitress import serve
import traceback
from config import DB_DIR

LOG_FILE = os.path.join(DB_DIR, 'startup.log')

def _log(message):
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f'[{datetime.now().isoformat(timespec="seconds")}] {message}\n')
    except OSError:
        pass

def start_flask():
    try:
        serve(app, host='127.0.0.1', port=5000, threads=8)
    except Exception:
        _log('Waitress failed to start:\n' + traceback.format_exc())

def wait_for_server(host='127.0.0.1', port=5000, timeout=15):
    """Block until Flask is actually accepting connections (or timeout).

    pywebview's window navigates once, immediately, with no retry -- so
    without this, the window can open a beat before Flask has bound the
    port and just sit on a blank page.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False

if __name__ == '__main__':
    def on_ready(window):
        """Runs in its own thread once pywebview's GUI loop is already
        pumping messages -- so the window is responsive immediately,
        never blocked waiting on Flask/waitress to come up.
        """
        try:
            Thread(target=start_flask, daemon=True).start()
            if wait_for_server():
                window.load_url('http://127.0.0.1:5000')
            else:
                _log('Timed out waiting for the local server to start.')
                window.load_html(
                    '<body style="background:#111;color:#eee;font-family:sans-serif;'
                    'padding:40px;">Could not start the local server in time.<br>'
                    f'See the log for details:<br><code>{LOG_FILE}</code></body>'
                )
        except Exception:
            tb = traceback.format_exc()
            _log('on_ready crashed:\n' + tb)
            window.load_html(
                '<body style="background:#111;color:#eee;font-family:monospace;'
                'white-space:pre-wrap;padding:40px;font-size:13px;">'
                f'Startup error:\n\n{tb}</body>'
            )

    api = DesktopApi()
    window = webview.create_window(
        APP_NAME,
        html='<body style="background:#111;color:#eee;font-family:sans-serif;'
             'padding:40px;">Starting VisionCraft&hellip;</body>',
        js_api=api,
        width=1280,
        height=800,
        min_size=(1024, 700),
    )
    _windows['main'] = window
    webview.start(on_ready, window, gui='edgechromium')
