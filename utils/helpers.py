import os
import random
import uuid
from datetime import datetime
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Only administrators can access that page.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return wrapper


def _next_code(model, column, prefix):
    last = model.query.order_by(model.id.desc()).first()
    n = (last.id + 1) if last else 1
    while model.query.filter(column == f"{prefix}-{n:04d}").first():
        n += 1
    return f"{prefix}-{n:04d}"


def generate_customer_code():
    from models import Customer
    return _next_code(Customer, Customer.customer_code, 'CUS')


def generate_frame_code():
    from models import Frame
    return _next_code(Frame, Frame.frame_code, 'FRM')


def generate_lens_code():
    from models import Lens
    return _next_code(Lens, Lens.lens_code, 'LNS')


def _dated_number(model, column, prefix):
    while True:
        num = f"{prefix}-{datetime.utcnow():%Y%m%d}-{random.randint(1000, 9999)}"
        if not model.query.filter(column == num).first():
            return num


def generate_order_number():
    from models import Order
    return _dated_number(Order, Order.order_number, 'ORD')


def generate_invoice_number():
    from models import Invoice
    return _dated_number(Invoice, Invoice.invoice_number, 'INV')


def save_uploaded_file(file, folder):
    """Save an uploaded image and return its file name (None if not a valid image)."""
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_IMAGES:
        return None
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}_{secure_filename(file.filename)}"
    file.save(os.path.join(folder, name))
    return name
