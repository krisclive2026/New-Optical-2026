from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='Staff')   # Admin / Staff
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'Admin'


class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    customer_code = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120))
    gender = db.Column(db.String(20))
    dob = db.Column(db.Date)
    address = db.Column(db.String(255))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    prescriptions = db.relationship('Prescription', backref='customer', lazy='dynamic', cascade='all, delete-orphan')
    orders = db.relationship('Order', backref='customer', lazy='dynamic', cascade='all, delete-orphan')
    invoices = db.relationship('Invoice', backref='customer', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='customer', lazy='dynamic', cascade='all, delete-orphan')


class Prescription(db.Model):
    __tablename__ = 'prescriptions'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    spherical_od = db.Column(db.String(20)); cyl_od = db.Column(db.String(20)); axis_od = db.Column(db.String(20)); add_od = db.Column(db.String(20))
    spherical_os = db.Column(db.String(20)); cyl_os = db.Column(db.String(20)); axis_os = db.Column(db.String(20)); add_os = db.Column(db.String(20))
    pd = db.Column(db.String(20)); near_pd = db.Column(db.String(20))
    doctor_name = db.Column(db.String(120))
    prescription_date = db.Column(db.Date, default=datetime.utcnow)
    next_test_date = db.Column(db.Date)
    notes = db.Column(db.Text)


class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    contact_person = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(120))
    address = db.Column(db.String(255))
    products_supplied = db.Column(db.String(255))
    notes = db.Column(db.Text)
    # frames = db.relationship('Frame', backref='supplier', lazy='dynamic')
    # lenses = db.relationship('Lens', backref='supplier', lazy='dynamic')


class Frame(db.Model):
    __tablename__ = 'frames'
    id = db.Column(db.Integer, primary_key=True)
    frame_code = db.Column(db.String(30), unique=True, nullable=False)
    brand = db.Column(db.String(80), nullable=False)
    model = db.Column(db.String(80), nullable=False)
    gender = db.Column(db.String(20), default='Unisex')
    frame_type = db.Column(db.String(30))
    material = db.Column(db.String(50))
    color = db.Column(db.String(50))
    size = db.Column(db.String(30))
    purchase_price = db.Column(db.Float, default=0.0)
    selling_price = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Integer, default=0)
    min_stock = db.Column(db.Integer, default=5)
    status = db.Column(db.String(20), default='In Stock')
    image_filename = db.Column(db.String(255))
    supplier_id = db.Column(db.String(50), nullable=True)

    @property
    def is_low_stock(self):
        return (self.quantity or 0) <= (self.min_stock or 0)


class Lens(db.Model):
    __tablename__ = 'lenses'
    id = db.Column(db.Integer, primary_key=True)
    lens_code = db.Column(db.String(30), unique=True, nullable=False)
    brand = db.Column(db.String(80), nullable=False)
    lens_type = db.Column(db.String(50), nullable=False)
    material = db.Column(db.String(50))
    index_val = db.Column(db.String(10))
    coating = db.Column(db.String(100))
    purchase_price = db.Column(db.Float, default=0.0)
    selling_price = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Integer, default=0)
    min_stock = db.Column(db.Integer, default=3)
    description = db.Column(db.Text)
    supplier_id = db.Column(db.String(50), nullable=True)

    @property
    def is_low_stock(self):
        return (self.quantity or 0) <= (self.min_stock or 0)


class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(30), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    prescription_id = db.Column(db.Integer, db.ForeignKey('prescriptions.id'))
    frame_id = db.Column(db.Integer, db.ForeignKey('frames.id'))
    lens_id = db.Column(db.Integer, db.ForeignKey('lenses.id'))
    quantity = db.Column(db.Integer, default=1)
    lens_details = db.Column(db.String(255))
    total_amount = db.Column(db.Float, default=0.0)
    discount = db.Column(db.Float, default=0.0)
    advance_payment = db.Column(db.Float, default=0.0)
    balance_amount = db.Column(db.Float, default=0.0)
    order_date = db.Column(db.Date, default=datetime.utcnow)
    expected_delivery_date = db.Column(db.Date)
    status = db.Column(db.String(30), default='New')
    notes = db.Column(db.Text)
    prescription = db.relationship('Prescription')
    frame = db.relationship('Frame')
    lens = db.relationship('Lens')


class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(40), unique=True, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    invoice_date = db.Column(db.Date, default=datetime.utcnow)
    frame_amount = db.Column(db.Float, default=0.0)
    lens_amount = db.Column(db.Float, default=0.0)
    other_charges = db.Column(db.Float, default=0.0)
    discount = db.Column(db.Float, default=0.0)
    tax_rate = db.Column(db.Float, default=0.0)
    tax_amount = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    balance_amount = db.Column(db.Float, default=0.0)
    payment_status = db.Column(db.String(20), default='Unpaid')
    payment_method = db.Column(db.String(30), default='Cash')
    notes = db.Column(db.Text)
    order = db.relationship('Order', backref=db.backref('invoice', uselist=False))
    payments = db.relationship('Payment', backref='invoice', lazy='dynamic', cascade='all, delete-orphan')

    def calculate_totals(self):
        subtotal = (self.frame_amount or 0) + (self.lens_amount or 0) + (self.other_charges or 0)
        taxable = max(subtotal - (self.discount or 0), 0)
        self.tax_amount = round(taxable * (self.tax_rate or 0) / 100, 2)
        self.total_amount = round(taxable + self.tax_amount, 2)
        self.balance_amount = max(round(self.total_amount - (self.paid_amount or 0), 2), 0.0)
        if self.balance_amount <= 0:
            self.payment_status = 'Paid'
        elif (self.paid_amount or 0) > 0:
            self.payment_status = 'Partial'
        else:
            self.payment_status = 'Unpaid'


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    amount_paid = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, default=datetime.utcnow)
    payment_method = db.Column(db.String(30), default='Cash')
    notes = db.Column(db.String(255))


class InventoryTransaction(db.Model):
    __tablename__ = 'inventory_transactions'
    id = db.Column(db.Integer, primary_key=True)
    item_type = db.Column(db.String(20), nullable=False)
    item_id = db.Column(db.Integer)
    item_name = db.Column(db.String(200))
    transaction_type = db.Column(db.String(30), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(100))
    notes = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
