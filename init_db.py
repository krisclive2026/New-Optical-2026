import os
from datetime import datetime, timedelta
from app import create_app
from models import db, User, Customer, Prescription, Supplier, Frame, Lens, Order, Invoice, Payment, InventoryTransaction
from utils.helpers import generate_customer_code, generate_frame_code, generate_lens_code, generate_order_number, generate_invoice_number

app = create_app()

def init_database():
    with app.app_context():
        print("Initializing Optical Store Management System Database...")
        db.create_all()

        # Check if default admin exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            print("Creating default Admin user ('admin' / 'admin123')...")
            admin = User(
                username='admin',
                name='System Administrator',
                email='admin@visioncraftoptical.com',
                role='Admin',
                is_active=True
            )
            admin.set_password('admin123')
            db.session.add(admin)

        # Check if default staff user exists
        staff = User.query.filter_by(username='staff').first()
        if not staff:
            print("Creating default Staff user ('staff' / 'staff123')...")
            staff = User(
                username='staff',
                name='Optician Staff',
                email='staff@visioncraftoptical.com',
                role='Staff',
                is_active=True
            )
            staff.set_password('staff123')
            db.session.add(staff)

        db.session.commit()

        # Seed initial suppliers if empty
        if Supplier.query.count() == 0:
            print("Seeding initial optical suppliers...")
            sup1 = Supplier(
                name="Luxottica Group Supplies",
                contact_person="Marco Rossi",
                phone="+1 (555) 111-2233",
                email="orders@luxotticagroup.com",
                address="100 Optical Way, Milan, IT",
                products_supplied="Ray-Ban, Oakley, Vogue Frames",
                notes="Primary frame distributor"
            )
            sup2 = Supplier(
                name="Essilor Vision Tech",
                contact_person="Claire Dupont",
                phone="+1 (555) 444-5566",
                email="supply@essilor.com",
                address="50 Lens Boulevard, Paris, FR",
                products_supplied="Single Vision, Progressive, Blue Cut Lenses",
                notes="High-index and anti-glare optical lenses"
            )
            sup3 = Supplier(
                name="Zeiss Optical Systems",
                contact_person="Hans Weber",
                phone="+1 (555) 777-8899",
                email="contact@zeissvision.de",
                address="12 Optik Strasse, Jena, DE",
                products_supplied="Precision Progressive & Photochromic Lenses",
                notes="Premium German lens manufacturer"
            )
            db.session.add_all([sup1, sup2, sup3])
            db.session.commit()

        # Seed initial starter frames if empty
        if Frame.query.count() == 0:
            print("Seeding initial optical frame inventory...")
            sup1 = Supplier.query.filter_by(name="Luxottica Group Supplies").first()
            f1 = Frame(
                frame_code=generate_frame_code(),
                brand="Ray-Ban",
                model="Wayfarer Classic RB2140",
                frame_type="Full Rim",
                gender="Unisex",
                material="Acetate",
                color="Black",
                size="50-22-150",
                purchase_price=80.0,
                selling_price=160.0,
                quantity=12,
                min_stock=3,
                supplier_id=sup1.id if sup1 else None,
                status="In Stock"
            )
            f2 = Frame(
                frame_code=generate_frame_code(),
                brand="Oakley",
                model="Holbrook OO9102",
                frame_type="Full Rim",
                gender="Men",
                material="O-Matter Plastic",
                color="Matte Black",
                size="55-18-137",
                purchase_price=70.0,
                selling_price=140.0,
                quantity=2,  # Low stock test
                min_stock=4,
                supplier_id=sup1.id if sup1 else None,
                status="In Stock"
            )
            f3 = Frame(
                frame_code=generate_frame_code(),
                brand="Vogue Eyewear",
                model="VO5331",
                frame_type="Semi-Rimless",
                gender="Women",
                material="Titanium",
                color="Rose Gold",
                size="52-16-140",
                purchase_price=65.0,
                selling_price=135.0,
                quantity=8,
                min_stock=2,
                supplier_id=sup1.id if sup1 else None,
                status="In Stock"
            )
            f4 = Frame(
                frame_code=generate_frame_code(),
                brand="Ray-Ban Junior",
                model="RB1536",
                frame_type="Full Rim",
                gender="Kids",
                material="Flex Acetate",
                color="Transparent Blue",
                size="46-16-130",
                purchase_price=45.0,
                selling_price=95.0,
                quantity=15,
                min_stock=3,
                supplier_id=sup1.id if sup1 else None,
                status="In Stock"
            )
            db.session.add_all([f1, f2, f3, f4])
            db.session.commit()

        # Seed initial starter lenses if empty
        if Lens.query.count() == 0:
            print("Seeding initial lens inventory...")
            sup2 = Supplier.query.filter_by(name="Essilor Vision Tech").first()
            sup3 = Supplier.query.filter_by(name="Zeiss Optical Systems").first()

            l1 = Lens(
                lens_code=generate_lens_code(),
                brand="Essilor Crizal",
                lens_type="Single Vision",
                material="CR-39 Standard",
                index_val="1.56",
                coating="Anti-Reflective + Anti-Glare",
                purchase_price=20.0,
                selling_price=50.0,
                quantity=25,
                min_stock=5,
                supplier_id=sup2.id if sup2 else None,
                description="High clarity single vision lens with blue shield"
            )
            l2 = Lens(
                lens_code=generate_lens_code(),
                brand="Essilor Prevencia",
                lens_type="Blue Cut",
                material="Polycarbonate",
                index_val="1.61",
                coating="Blue Shield + UV400",
                purchase_price=35.0,
                selling_price=85.0,
                quantity=18,
                min_stock=5,
                supplier_id=sup2.id if sup2 else None,
                description="Digital screen protection blue light filtering lens"
            )
            l3 = Lens(
                lens_code=generate_lens_code(),
                brand="Zeiss SmartLife",
                lens_type="Progressive",
                material="High Index 1.67",
                index_val="1.67",
                coating="LotuTec Hydrophobic",
                purchase_price=90.0,
                selling_price=220.0,
                quantity=3, # Low stock test
                min_stock=5,
                supplier_id=sup3.id if sup3 else None,
                description="Custom digital progressive lens for all distances"
            )
            l4 = Lens(
                lens_code=generate_lens_code(),
                brand="Zeiss Photofusion",
                lens_type="Photochromic",
                material="CR-39",
                index_val="1.56",
                coating="Transit Auto-Darkening",
                purchase_price=55.0,
                selling_price=130.0,
                quantity=10,
                min_stock=3,
                supplier_id=sup3.id if sup3 else None,
                description="Light-adaptive photochromic lens (Turns dark outdoor)"
            )
            db.session.add_all([l1, l2, l3, l4])
            db.session.commit()

        print("Database initialization complete successfully!")

if __name__ == '__main__':
    init_database()
