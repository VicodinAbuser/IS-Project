"""Fill the database with demo data. Run: python seed.py   (add --reset to wipe first)"""
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

from app.database import Base, SessionLocal, engine
from app.models import (Category, Delivery, DeliveryStatus, Inventory, MovementType, Order, OrderItem,
                        OrderStatus, Outlet, Payment, PaymentStatus, Product, Role, StockMovement, Supplier, User)
from app.security import hash_password

if "--reset" in sys.argv:
    Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

random.seed(42)
db = SessionLocal()
if db.query(User).count():
    print("Database already has data. Use: python seed.py --reset")
    sys.exit(0)

admin = User(name="Store Admin", email="admin@inventory.com", password_hash=hash_password("admin123"),
             role=Role.ADMIN)
customers = [User(name=n, email=e, password_hash=hash_password("customer123"), role=Role.CUSTOMER,
                  phone="98765" + str(43210 + i), address=a)
             for i, (n, e, a) in enumerate([
                 ("Demo Customer", "customer@inventory.com", "12 Hill Road, Bandra, Mumbai"),
                 ("Priya Sharma", "priya@example.com", "45 MG Road, Pune"),
                 ("Rahul Verma", "rahul@example.com", "8 Indiranagar, Bengaluru"),
                 ("Aisha Khan", "aisha@example.com", "22 Connaught Place, Delhi")])]
db.add_all([admin, *customers])

outlets = [Outlet(name="Mumbai Central", city="Mumbai", address="Lower Parel"),
           Outlet(name="Pune Hub", city="Pune", address="Hinjewadi"),
           Outlet(name="Bengaluru Store", city="Bengaluru", address="Koramangala"),
           Outlet(name="Delhi Warehouse", city="Delhi", address="Okhla")]
cats = {n: Category(name=n) for n in ["Electronics", "Stationery", "Home & Kitchen", "Apparel"]}
sups = [Supplier(name="TechSource Pvt Ltd", contact_email="sales@techsource.example", phone="022-4000100"),
        Supplier(name="PaperWorks Co", contact_email="orders@paperworks.example", phone="020-3000200"),
        Supplier(name="HomeEssentials", contact_email="hello@homeessentials.example", phone="080-2000300")]
db.add_all([*outlets, *cats.values(), *sups])

catalog = [
    ("EL-001", "Wireless Mouse", "Electronics", 0, 699, "2.4GHz ergonomic mouse"),
    ("EL-002", "Bluetooth Headphones", "Electronics", 0, 2499, "Over-ear, 30h battery"),
    ("EL-003", "USB-C Charger 65W", "Electronics", 0, 1599, "Fast charging GaN adapter"),
    ("EL-004", "Mechanical Keyboard", "Electronics", 0, 3999, "Hot-swappable switches"),
    ("EL-005", "Power Bank 20000mAh", "Electronics", 0, 1899, "Dual USB output"),
    ("ST-001", "A4 Notebook (Pack of 5)", "Stationery", 1, 349, "200 pages each, ruled"),
    ("ST-002", "Gel Pens (Pack of 10)", "Stationery", 1, 199, "Smooth 0.5mm tip"),
    ("ST-003", "Desk Organizer", "Stationery", 1, 549, "Bamboo, 5 compartments"),
    ("HK-001", "Steel Water Bottle 1L", "Home & Kitchen", 2, 599, "Insulated, keeps cold 24h"),
    ("HK-002", "Non-stick Frying Pan", "Home & Kitchen", 2, 1299, "28cm, induction ready"),
    ("HK-003", "Coffee Mug Set", "Home & Kitchen", 2, 799, "Set of 4 ceramic mugs"),
    ("AP-001", "Cotton T-Shirt", "Apparel", None, 499, "Unisex, 100% cotton"),
    ("AP-002", "Hoodie", "Apparel", None, 1499, "Fleece-lined pullover"),
]
products = [Product(sku=s, name=n, category=cats[c], supplier=sups[sp] if sp is not None else None,
                    price=p, description=d, reorder_level=10,
                    image_url=f"https://picsum.photos/seed/{s}/400/300")
            for s, n, c, sp, p, d in catalog]
db.add_all(products)
db.flush()

now = datetime.now(timezone.utc)
start = datetime(now.year - 1, 1, 1, tzinfo=timezone.utc)
stock = {}
for p in products:
    for o in outlets:
        qty = random.randint(60, 160)
        stock[(p.id, o.id)] = qty
        db.add(StockMovement(product_id=p.id, outlet_id=o.id, change=qty, movement_type=MovementType.RESTOCK,
                             user_id=admin.id, note="Opening stock", created_at=start))

# ~260 historical orders spread from January last year until today, for quarterly reports.
span = (now - start).total_seconds()
for _ in range(260):
    created = start + timedelta(seconds=random.random() * span)
    cust, outlet = random.choice(customers), random.choice(outlets)
    picks = random.sample(products, random.randint(1, 3))
    order = Order(customer_id=cust.id, outlet_id=outlet.id, total_amount=0, shipping_address=cust.address,
                  status=OrderStatus.PAID, created_at=created)
    db.add(order)
    db.flush()
    total = 0
    for p in picks:
        q = random.randint(1, 3)
        if stock[(p.id, outlet.id)] - q < 5:
            continue
        stock[(p.id, outlet.id)] -= q
        total += float(p.price) * q
        db.add(OrderItem(order_id=order.id, product_id=p.id, quantity=q, unit_price=p.price))
        db.add(StockMovement(product_id=p.id, outlet_id=outlet.id, change=-q, movement_type=MovementType.SALE,
                             order_id=order.id, user_id=cust.id, created_at=created))
    if total == 0:
        db.delete(order)
        continue
    order.total_amount = round(total, 2)
    age = (now - created).days
    delivery = DeliveryStatus.DELIVERED if age > 7 else random.choice(
        [DeliveryStatus.PACKED, DeliveryStatus.SHIPPED, DeliveryStatus.OUT_FOR_DELIVERY])
    db.add(Payment(order_id=order.id, amount=order.total_amount, method=random.choice(["CARD", "UPI", "NETBANKING"]),
                   status=PaymentStatus.SUCCESS, transaction_ref="TXN-" + uuid.uuid4().hex[:12].upper(),
                   updated_at=created))
    db.add(Delivery(order_id=order.id, status=delivery, courier="BlueDart" if delivery != DeliveryStatus.PACKED else None,
                    tracking_number=f"BD{order.id:08d}" if delivery != DeliveryStatus.PACKED else None,
                    updated_at=created))

# Make a few items low on stock so the alert shows up in the demo.
for p, o in [(products[1], outlets[0]), (products[3], outlets[2]), (products[9], outlets[1])]:
    diff = 4 - stock[(p.id, o.id)]
    stock[(p.id, o.id)] = 4
    db.add(StockMovement(product_id=p.id, outlet_id=o.id, change=diff, movement_type=MovementType.ADJUSTMENT,
                         user_id=admin.id, note="Stock audit correction"))

for (pid, oid), qty in stock.items():
    db.add(Inventory(product_id=pid, outlet_id=oid, quantity=qty))

db.commit()
print(f"Seeded {len(products)} products, {len(outlets)} outlets, {db.query(Order).count()} orders.")
print("Admin login:    admin@inventory.com / admin123")
print("Customer login: customer@inventory.com / customer123")
