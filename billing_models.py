"""Bill line items (kept separate so models.py does not need to change)."""
from models import db


class InvoiceItem(db.Model):
    __tablename__ = 'invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, index=True, nullable=False)
    item_type = db.Column(db.String(20), nullable=False)      # Frame / Lens / Custom
    item_id = db.Column(db.Integer)                            # product id (None for typed items)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    unit_price = db.Column(db.Float, nullable=False, default=0.0)


def get_bill_items(invoice):
    """Return the bill lines as dicts. Old invoices (no saved lines) are rebuilt from their amounts."""
    rows = InvoiceItem.query.filter_by(invoice_id=invoice.id).order_by(InvoiceItem.id).all()
    if rows:
        return [dict(type=r.item_type, description=r.description, quantity=r.quantity,
                     unit_price=r.unit_price, total=round(r.quantity * r.unit_price, 2)) for r in rows]
    items, order = [], invoice.order
    if invoice.frame_amount:
        name = f"{order.frame.brand} {order.frame.model}" if order and order.frame else "Frame"
        items.append(dict(type='Frame', description=name, quantity=1,
                          unit_price=invoice.frame_amount, total=invoice.frame_amount))
    if invoice.lens_amount:
        qty = (order.quantity if order and order.quantity else 1)
        name = f"{order.lens.brand} - {order.lens.lens_type}" if order and order.lens else "Lens"
        items.append(dict(type='Lens', description=name, quantity=qty,
                          unit_price=round(invoice.lens_amount / qty, 2), total=invoice.lens_amount))
    if invoice.other_charges:
        items.append(dict(type='Custom', description='Other charges', quantity=1,
                          unit_price=invoice.other_charges, total=invoice.other_charges))
    return items


NEW_INVOICES_SQL = """
CREATE TABLE invoices_new (
    id INTEGER NOT NULL PRIMARY KEY,
    invoice_number VARCHAR(40) NOT NULL UNIQUE,
    order_id INTEGER REFERENCES orders (id),
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    invoice_date DATE, frame_amount FLOAT, lens_amount FLOAT, other_charges FLOAT,
    discount FLOAT, tax_rate FLOAT, tax_amount FLOAT, total_amount FLOAT,
    paid_amount FLOAT, balance_amount FLOAT, payment_status VARCHAR(20),
    payment_method VARCHAR(30), notes TEXT
)"""


def ensure_invoice_order_nullable(db):
    """Older databases have invoices.order_id NOT NULL, which blocks bills that are not
    tied to an order. Rebuild the invoices table once (keeping every row) to allow NULL."""
    raw = db.engine.raw_connection()
    try:
        cur = raw.cursor()
        info = cur.execute("PRAGMA table_info(invoices)").fetchall()
        order_col = [c for c in info if c[1] == 'order_id']
        if not order_col or not order_col[0][3]:      # column missing or already nullable
            return
        new_cols = ['id', 'invoice_number', 'order_id', 'customer_id', 'invoice_date', 'frame_amount',
                    'lens_amount', 'other_charges', 'discount', 'tax_rate', 'tax_amount', 'total_amount',
                    'paid_amount', 'balance_amount', 'payment_status', 'payment_method', 'notes']
        keep = ', '.join(c for c in new_cols if c in {r[1] for r in info})
        cur.execute("DROP TABLE IF EXISTS invoices_new")
        cur.execute(NEW_INVOICES_SQL)
        cur.execute(f"INSERT INTO invoices_new ({keep}) SELECT {keep} FROM invoices")
        cur.execute("DROP TABLE invoices")
        cur.execute("ALTER TABLE invoices_new RENAME TO invoices")
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
