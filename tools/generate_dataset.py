"""Generate the large demo dataset (50,000 customers) as one CSV file per table.

    python tools/generate_dataset.py          -> writes database/dataset/*.csv

The data is made by *simulating* the shop day by day, following the same rules as the
PL/SQL package INVENTORY_PKG, so every table agrees with every other table:
  - stock never goes below 0, and INVENTORY.QUANTITY = sum of STOCK_MOVEMENTS for that row
  - every order item has a SALE movement; cancelled orders have CANCEL movements, returns RETURN
  - ORDERS.TOTAL_AMOUNT = sum of its items, and PAYMENTS.AMOUNT = the order total
  - order / payment / delivery statuses only appear in combinations the package can produce
  - all dates are in the right order (sign-up -> order -> payment -> shipping -> delivery)
  - every user has a profile (USER_PROFILES); every customer has a CUSTOMER_PROFILES row
The same seed always gives the same files. Check them with: python tools/validate_dataset.py
"""
import csv
import heapq
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "database" / "dataset"

SEED = 2026
N_CUSTOMERS = 50_000
START = datetime(2025, 1, 1)             # first day of trading
END = datetime(2026, 11, 15, 20, 0, 0)   # "now" for this dataset; nothing happens after it
PAYMENT_TIMEOUT_MIN = 30                 # inventory_pkg.c_payment_timeout_minutes

# bcrypt hashes, the same as 03_seed_data.sql: admin123 / customer123
ADMIN_HASH = "$2b$10$LxPkTj7w6i8MEudhIh0vDONnJSsEVeOpKSCrTwlZHPF5niPB5exZG"
CUSTOMER_HASH = "$2b$10$GhAr6Ar5G3snQ0cIxvbb2.Sv/J.tXeu98/iYCp6sDq2X3/xZWfSZm"

rng = random.Random(SEED)

# ----------------------------------------------------------------- reference data
OUTLETS = [  # name, city, address
    ("Mumbai Central", "Mumbai", "Lower Parel"),
    ("Pune Hub", "Pune", "Hinjewadi"),
    ("Bengaluru Store", "Bengaluru", "Koramangala"),
    ("Delhi Warehouse", "Delhi", "Okhla"),
    ("Chennai Store", "Chennai", "T. Nagar"),
    ("Hyderabad Hub", "Hyderabad", "HITEC City"),
    ("Kolkata Store", "Kolkata", "Salt Lake"),
    ("Ahmedabad Outlet", "Ahmedabad", "Navrangpura"),
    ("Jaipur Outlet", "Jaipur", "Malviya Nagar"),
    ("Kochi Store", "Kochi", "Edappally"),
]

CATEGORIES = ["Electronics", "Stationery", "Home & Kitchen", "Apparel",
              "Sports & Fitness", "Beauty & Personal Care", "Books", "Toys & Games"]

SUPPLIERS = [  # name, email, phone
    ("TechSource Pvt Ltd", "sales@techsource.example", "022-4000100"),
    ("PaperWorks Co", "orders@paperworks.example", "020-3000200"),
    ("HomeEssentials", "hello@homeessentials.example", "080-2000300"),
    ("GadgetHub Distributors", "supply@gadgethub.example", "040-4100200"),
    ("StyleThread Apparel", "b2b@stylethread.example", "079-2600300"),
    ("FitLife Sports", "orders@fitlife.example", "044-2800400"),
    ("GlowCare Cosmetics", "trade@glowcare.example", "033-2400500"),
    ("ReadWell Books", "wholesale@readwell.example", "011-4300600"),
    ("PlayTime Toys", "sales@playtime.example", "0141-2700700"),
    ("KitchenKraft", "orders@kitchenkraft.example", "0484-2500800"),
    ("OfficeMate Supplies", "hello@officemate.example", "022-4200900"),
    ("UrbanWear Textiles", "sales@urbanwear.example", "080-2901000"),
]

# sku, name, category, supplier (None = no supplier), price, description.
# The first 13 are the same as 03_seed_data.sql.
PRODUCTS = [
    ("EL-001", "Wireless Mouse", "Electronics", "TechSource Pvt Ltd", 699, "2.4GHz ergonomic mouse"),
    ("EL-002", "Bluetooth Headphones", "Electronics", "TechSource Pvt Ltd", 2499, "Over-ear, 30h battery"),
    ("EL-003", "USB-C Charger 65W", "Electronics", "TechSource Pvt Ltd", 1599, "Fast charging GaN adapter"),
    ("EL-004", "Mechanical Keyboard", "Electronics", "TechSource Pvt Ltd", 3999, "Hot-swappable switches"),
    ("EL-005", "Power Bank 20000mAh", "Electronics", "TechSource Pvt Ltd", 1899, "Dual USB output"),
    ("ST-001", "A4 Notebook (Pack of 5)", "Stationery", "PaperWorks Co", 349, "200 pages each, ruled"),
    ("ST-002", "Gel Pens (Pack of 10)", "Stationery", "PaperWorks Co", 199, "Smooth 0.5mm tip"),
    ("ST-003", "Desk Organizer", "Stationery", "PaperWorks Co", 549, "Bamboo, 5 compartments"),
    ("HK-001", "Steel Water Bottle 1L", "Home & Kitchen", "HomeEssentials", 599, "Insulated, keeps cold 24h"),
    ("HK-002", "Non-stick Frying Pan", "Home & Kitchen", "HomeEssentials", 1299, "28cm, induction ready"),
    ("HK-003", "Coffee Mug Set", "Home & Kitchen", "HomeEssentials", 799, "Set of 4 ceramic mugs"),
    ("AP-001", "Cotton T-Shirt", "Apparel", None, 499, "Unisex, 100% cotton"),
    ("AP-002", "Hoodie", "Apparel", None, 1499, "Fleece-lined pullover"),
    # --- added for the large dataset
    ("EL-006", "Smart Watch", "Electronics", "GadgetHub Distributors", 4999, "AMOLED display, heart-rate monitor"),
    ("EL-007", "Wireless Earbuds", "Electronics", "GadgetHub Distributors", 1999, "Bluetooth 5.3, 24h with case"),
    ("EL-008", "Portable Bluetooth Speaker", "Electronics", "GadgetHub Distributors", 2299, "Waterproof, 12h battery"),
    ("EL-009", "Full HD Webcam", "Electronics", "TechSource Pvt Ltd", 2799, "1080p with dual microphones"),
    ("EL-010", "32GB USB Flash Drive", "Electronics", "TechSource Pvt Ltd", 399, "USB 3.2, metal body"),
    ("EL-011", "1TB External SSD", "Electronics", "GadgetHub Distributors", 7499, "Up to 1050 MB/s"),
    ("EL-012", "LED Desk Lamp", "Electronics", "TechSource Pvt Ltd", 1199, "3 colour modes, USB charging port"),
    ("EL-013", "HDMI Cable 2m", "Electronics", "TechSource Pvt Ltd", 349, "4K 60Hz, braided"),
    ("EL-014", "Wi-Fi Router AX1800", "Electronics", "GadgetHub Distributors", 3499, "Dual-band Wi-Fi 6"),
    ("EL-015", "Laptop Stand", "Electronics", "GadgetHub Distributors", 1299, "Aluminium, adjustable height"),
    ("ST-004", "Sticky Notes (Pack of 6)", "Stationery", "OfficeMate Supplies", 149, "3x3 inch, assorted colours"),
    ("ST-005", "Highlighter Set (6 colours)", "Stationery", "OfficeMate Supplies", 179, "Chisel tip, quick-dry"),
    ("ST-006", "Spiral Diary 2026", "Stationery", "PaperWorks Co", 299, "Dated, one day per page"),
    ("ST-007", "Scientific Calculator", "Stationery", "OfficeMate Supplies", 899, "417 functions, solar + battery"),
    ("ST-008", "Stapler with 1000 Pins", "Stationery", "OfficeMate Supplies", 229, "Full-strip, 20 sheet capacity"),
    ("ST-009", "Drawing Pencil Set", "Stationery", "PaperWorks Co", 259, "12 grades, 6B to 4H"),
    ("ST-010", "Document File Folders (Pack of 10)", "Stationery", "OfficeMate Supplies", 249, "A4 size, button closure"),
    ("ST-011", "Whiteboard 2x3 ft", "Stationery", "OfficeMate Supplies", 1099, "Magnetic, with marker and duster"),
    ("ST-012", "Fountain Pen", "Stationery", "PaperWorks Co", 649, "Medium nib, refillable converter"),
    ("HK-004", "Pressure Cooker 5L", "Home & Kitchen", "KitchenKraft", 2199, "Stainless steel, induction base"),
    ("HK-005", "Glass Storage Containers (Set of 3)", "Home & Kitchen", "KitchenKraft", 899, "Airtight, microwave safe"),
    ("HK-006", "Electric Kettle 1.5L", "Home & Kitchen", "HomeEssentials", 1149, "Auto shut-off, 1500W"),
    ("HK-007", "Chef Knife 8 inch", "Home & Kitchen", "KitchenKraft", 999, "High-carbon stainless steel"),
    ("HK-008", "Cotton Bedsheet Double", "Home & Kitchen", "HomeEssentials", 1399, "With 2 pillow covers"),
    ("HK-009", "Mixer Grinder 750W", "Home & Kitchen", "KitchenKraft", 3299, "3 jars, 5-year motor warranty"),
    ("HK-010", "Lunch Box (3 compartments)", "Home & Kitchen", "HomeEssentials", 549, "Leak-proof, insulated bag"),
    ("HK-011", "Bath Towel Set", "Home & Kitchen", "HomeEssentials", 899, "2 towels, 500 GSM cotton"),
    ("HK-012", "Dinner Plate Set", "Home & Kitchen", "KitchenKraft", 1599, "Set of 6, melamine"),
    ("AP-003", "Denim Jeans", "Apparel", "UrbanWear Textiles", 1799, "Slim fit, stretchable"),
    ("AP-004", "Formal Shirt", "Apparel", "StyleThread Apparel", 1199, "Cotton blend, wrinkle-free"),
    ("AP-005", "Kurta", "Apparel", "StyleThread Apparel", 999, "Printed cotton, regular fit"),
    ("AP-006", "Running Shoes", "Apparel", "UrbanWear Textiles", 2999, "Cushioned sole, breathable mesh"),
    ("AP-007", "Winter Jacket", "Apparel", "UrbanWear Textiles", 3499, "Water-resistant, padded"),
    ("AP-008", "Track Pants", "Apparel", "StyleThread Apparel", 899, "Quick-dry, zip pockets"),
    ("AP-009", "Socks (Pack of 5)", "Apparel", "UrbanWear Textiles", 299, "Cotton, ankle length"),
    ("AP-010", "Baseball Cap", "Apparel", "StyleThread Apparel", 449, "Adjustable strap"),
    ("SP-001", "Yoga Mat 6mm", "Sports & Fitness", "FitLife Sports", 799, "Anti-slip, with carry strap"),
    ("SP-002", "Dumbbell Set 10kg", "Sports & Fitness", "FitLife Sports", 1899, "Adjustable, PVC coated"),
    ("SP-003", "Skipping Rope", "Sports & Fitness", "FitLife Sports", 249, "Ball bearing, adjustable length"),
    ("SP-004", "Cricket Bat (Kashmir Willow)", "Sports & Fitness", "FitLife Sports", 1599, "Full size, with cover"),
    ("SP-005", "Football Size 5", "Sports & Fitness", "FitLife Sports", 699, "Machine stitched"),
    ("SP-006", "Badminton Racquet Pair", "Sports & Fitness", "FitLife Sports", 1299, "With 3 shuttlecocks"),
    ("SP-007", "Resistance Bands Set", "Sports & Fitness", "FitLife Sports", 599, "5 levels, with door anchor"),
    ("SP-008", "Gym Bag", "Sports & Fitness", "FitLife Sports", 999, "Shoe compartment, 40L"),
    ("SP-009", "Sipper Bottle 750ml", "Sports & Fitness", "FitLife Sports", 349, "BPA-free"),
    ("SP-010", "Fitness Tracker Band", "Sports & Fitness", "GadgetHub Distributors", 1799, "Step, sleep and SpO2 tracking"),
    ("BC-001", "Face Wash 150ml", "Beauty & Personal Care", "GlowCare Cosmetics", 249, "Neem and tulsi, oil control"),
    ("BC-002", "Moisturiser 200ml", "Beauty & Personal Care", "GlowCare Cosmetics", 349, "Non-greasy, SPF 15"),
    ("BC-003", "Shampoo 340ml", "Beauty & Personal Care", "GlowCare Cosmetics", 299, "Anti-dandruff"),
    ("BC-004", "Sunscreen SPF 50", "Beauty & Personal Care", "GlowCare Cosmetics", 449, "Matte finish, 50g"),
    ("BC-005", "Electric Trimmer", "Beauty & Personal Care", "GadgetHub Distributors", 1499, "60 min runtime, 20 length settings"),
    ("BC-006", "Hair Dryer 1200W", "Beauty & Personal Care", "GadgetHub Distributors", 1199, "2 heat settings, foldable"),
    ("BC-007", "Perfume 100ml", "Beauty & Personal Care", "GlowCare Cosmetics", 899, "Long-lasting eau de parfum"),
    ("BC-008", "Lip Balm (Pack of 3)", "Beauty & Personal Care", "GlowCare Cosmetics", 199, "Shea butter"),
    ("BC-009", "Toothbrush (Pack of 4)", "Beauty & Personal Care", "GlowCare Cosmetics", 179, "Soft bristles"),
    ("BC-010", "Hand Wash Refill 750ml", "Beauty & Personal Care", "GlowCare Cosmetics", 159, "Antibacterial"),
    ("BK-001", "Database System Concepts", "Books", "ReadWell Books", 899, "Textbook, 7th edition, paperback"),
    ("BK-002", "Learning Python", "Books", "ReadWell Books", 1299, "Beginner to intermediate guide"),
    ("BK-003", "Management Information Systems", "Books", "ReadWell Books", 799, "Textbook, paperback"),
    ("BK-004", "The Art of Problem Solving", "Books", "ReadWell Books", 499, "Puzzles and strategies"),
    ("BK-005", "Indian History: A Short Guide", "Books", "ReadWell Books", 399, "Illustrated, paperback"),
    ("BK-006", "Personal Finance Basics", "Books", "ReadWell Books", 349, "Budgeting, saving and investing"),
    ("BK-007", "Children's Story Collection", "Books", "ReadWell Books", 299, "50 bedtime stories"),
    ("BK-008", "English Grammar Workbook", "Books", "ReadWell Books", 279, "Exercises with answers"),
    ("BK-009", "Cookbook: Everyday Indian Meals", "Books", "ReadWell Books", 599, "100 recipes, colour photos"),
    ("BK-010", "Quantitative Aptitude Guide", "Books", "ReadWell Books", 649, "For competitive exams"),
    ("TG-001", "Building Blocks Set (500 pcs)", "Toys & Games", "PlayTime Toys", 1199, "Ages 6+, compatible bricks"),
    ("TG-002", "Chess Board Set", "Toys & Games", "PlayTime Toys", 699, "Wooden, folding board"),
    ("TG-003", "Jigsaw Puzzle 1000 pcs", "Toys & Games", "PlayTime Toys", 599, "Landscape scene"),
    ("TG-004", "Remote Control Car", "Toys & Games", "PlayTime Toys", 1899, "Rechargeable, 2.4GHz"),
    ("TG-005", "Board Game: Business Tycoon", "Toys & Games", "PlayTime Toys", 799, "2-6 players"),
    ("TG-006", "Soft Toy Teddy Bear", "Toys & Games", "PlayTime Toys", 499, "30cm, washable"),
    ("TG-007", "Rubik's-style Speed Cube", "Toys & Games", "PlayTime Toys", 299, "3x3, smooth turning"),
    ("TG-008", "Art and Craft Kit", "Toys & Games", "PlayTime Toys", 899, "Colours, clay and stencils"),
    ("TG-009", "Card Game: UNO-style Colours", "Toys & Games", "PlayTime Toys", 199, "112 cards"),
    ("TG-010", "Kids Science Kit", "Toys & Games", "PlayTime Toys", 1299, "25 experiments, ages 8+"),
]
INACTIVE_SKUS = {"EL-013", "BK-005", "TG-009"}   # products later withdrawn from sale (is_active = 0)
LOW_STOCK_DEMO = [("EL-002", "Mumbai Central"), ("EL-004", "Bengaluru Store"), ("HK-002", "Pune Hub")]

FIRST_NAMES = """Aarav Vivaan Aditya Vihaan Arjun Sai Reyansh Ayaan Krishna Ishaan Shaurya Atharv Advik Pranav
Advaith Aryan Dhruv Kabir Ritvik Aarush Kayaan Darsh Veer Rohan Rahul Amit Sanjay Vikram Karan Nikhil Manish
Rajesh Suresh Ramesh Anil Sunil Deepak Gaurav Harsh Varun Yash Siddharth Kunal Mohit Akash Abhishek Ankit Tarun
Naveen Pradeep Vinay Ajay Vijay Arvind Ashok Mahesh Ganesh Kiran Prakash Rakesh Sachin Sandeep Tushar Uday
Aadhya Ananya Diya Saanvi Aanya Pari Anika Navya Myra Sara Ira Ishita Kavya Riya Priya Pooja Neha Sneha Anjali
Divya Shreya Meera Nisha Aisha Fatima Zara Sana Ayesha Sakshi Tanvi Shruti Swati Rashmi Kritika Megha Nidhi
Payal Komal Jyoti Lakshmi Deepa Geeta Sunita Anita Kavita Rekha Seema Usha Vandana Preeti Simran Harpreet
Gurpreet Manpreet Jaspreet Arun Bharat Chirag Dev Faisal Imran Irfan Javed Salman Farhan Joseph Thomas Mathew
George Anthony Mary Grace Elizabeth Ritu Shalini Madhuri Aparna Bhavna Charu Esha Hema Jaya Lata Mala Nandini
Padma Radha Sarita Uma Vidya Yamini Zoya""".split()
LAST_NAMES = """Sharma Verma Gupta Singh Kumar Patel Shah Mehta Joshi Desai Iyer Iyengar Nair Menon Pillai Reddy Rao
Naidu Chowdary Das Bose Banerjee Chatterjee Mukherjee Ghosh Sen Dutta Roy Saha Kulkarni Deshpande Patil Jadhav
Pawar Shinde More Gaikwad Khan Ansari Qureshi Siddiqui Shaikh Sheikh Malik Mirza Agarwal Bansal Goyal Jain
Khandelwal Maheshwari Mittal Saxena Srivastava Tiwari Tripathi Pandey Mishra Dubey Shukla Yadav Chauhan Rathore
Thakur Bhatt Trivedi Vyas Parikh Kapoor Khanna Malhotra Arora Chopra Bhatia Sethi Anand Gill Sandhu Dhillon
Grewal Sidhu Fernandes D'Souza Pereira Rodrigues Thomas George Kurian Varghese Krishnan Subramanian
Venkatesh Raman Narayanan Hegde Shetty Kamath Bhat Pai Prabhu""".split()

# Customer cities: city -> (weight, areas, pincode prefix, outlet that serves it)
CITIES = {
    "Mumbai": (14, ["Andheri West", "Bandra", "Powai", "Malad", "Dadar", "Goregaon East", "Borivali", "Chembur"], "400", "Mumbai Central"),
    "Pune": (8, ["Kothrud", "Baner", "Viman Nagar", "Hadapsar", "Wakad", "Aundh", "Kharadi"], "411", "Pune Hub"),
    "Bengaluru": (13, ["Indiranagar", "Whitefield", "HSR Layout", "Jayanagar", "Marathahalli", "Electronic City", "Hebbal"], "560", "Bengaluru Store"),
    "Delhi": (13, ["Connaught Place", "Dwarka", "Rohini", "Saket", "Lajpat Nagar", "Karol Bagh", "Janakpuri"], "110", "Delhi Warehouse"),
    "Chennai": (9, ["Adyar", "Anna Nagar", "Velachery", "T. Nagar", "Tambaram", "Porur"], "600", "Chennai Store"),
    "Hyderabad": (9, ["Gachibowli", "Madhapur", "Banjara Hills", "Kukatpally", "Secunderabad", "Kondapur"], "500", "Hyderabad Hub"),
    "Kolkata": (7, ["Salt Lake", "Park Street", "Ballygunge", "New Town", "Howrah", "Behala"], "700", "Kolkata Store"),
    "Ahmedabad": (5, ["Navrangpura", "Satellite", "Bopal", "Maninagar", "Vastrapur"], "380", "Ahmedabad Outlet"),
    "Jaipur": (4, ["Malviya Nagar", "Vaishali Nagar", "C-Scheme", "Mansarovar"], "302", "Jaipur Outlet"),
    "Kochi": (3, ["Edappally", "Kakkanad", "Vyttila", "Fort Kochi"], "682", "Kochi Store"),
    "Thane": (3, ["Ghodbunder Road", "Naupada", "Kolshet"], "400", "Mumbai Central"),
    "Navi Mumbai": (2, ["Vashi", "Nerul", "Kharghar"], "400", "Mumbai Central"),
    "Gurugram": (3, ["DLF Phase 2", "Sohna Road", "Sector 56"], "122", "Delhi Warehouse"),
    "Noida": (3, ["Sector 62", "Sector 18", "Sector 137"], "201", "Delhi Warehouse"),
    "Mysuru": (1, ["Vijayanagar", "Kuvempunagar"], "570", "Bengaluru Store"),
    "Coimbatore": (1, ["RS Puram", "Peelamedu"], "641", "Chennai Store"),
    "Surat": (1, ["Adajan", "Vesu"], "395", "Ahmedabad Outlet"),
    "Lucknow": (1, ["Gomti Nagar", "Hazratganj"], "226", "Delhi Warehouse"),
}
STREETS = ["MG Road", "Station Road", "Main Road", "Park Avenue", "Gandhi Nagar", "Nehru Street", "Lake View Road",
           "Temple Street", "Market Road", "Church Street", "Hill Road", "Ring Road", "1st Cross", "2nd Main",
           "Link Road", "College Road", "Shivaji Path", "Sardar Patel Marg"]
BUILDINGS = ["Sai Residency", "Green Park Apartments", "Lotus Towers", "Shanti Niketan", "Royal Heights",
             "Sunrise Enclave", "Palm Grove", "Krishna Kunj", "Silver Oak", "Gulmohar Society"]
EMAIL_DOMAINS = ["example.com", "example.in", "example.org", "mail.example", "inbox.example"]
COURIERS = [("BlueDart", "BD"), ("Delhivery", "DL"), ("DTDC", "DT"), ("Ecom Express", "EC"), ("XpressBees", "XB")]
# Access control: the same reference rows as the end of database/01_schema.sql
PROFILES = [  # code, name, description, is_staff
    ("ADMIN", "Administrator", "Full access, including users and access rights", 1),
    ("STORE_MANAGER", "Store manager", "Runs the outlets: catalogue, stock, orders and reports", 1),
    ("WAREHOUSE_STAFF", "Warehouse staff", "Receives and moves stock, packs and ships orders", 1),
    ("CUSTOMER", "Customer", "Shops online and tracks their own orders", 0),
]
PERMISSIONS = [  # code, name, module, access_type, description
    ("CATALOG_READ", "View products", "CATALOG", "READ", "See products, prices, categories and outlets"),
    ("CATALOG_WRITE", "Manage products", "CATALOG", "WRITE", "Add, edit and hide products; add outlets"),
    ("ORDER_PLACE", "Place orders", "ORDERS", "WRITE", "Buy, pay for and cancel own orders"),
    ("ORDER_READ_OWN", "View own orders", "ORDERS", "READ", "See own orders, payments and deliveries"),
    ("ORDER_READ_ALL", "View all orders", "ORDERS", "READ", "See every customer's orders"),
    ("ORDER_MANAGE", "Manage orders", "ORDERS", "WRITE", "Update deliveries, accept returns, cancel any order"),
    ("STOCK_READ", "View stock", "INVENTORY", "READ", "See stock per outlet, low stock and the movement log"),
    ("STOCK_WRITE", "Change stock", "INVENTORY", "WRITE", "Restock, adjust and transfer stock"),
    ("REPORT_VIEW", "View reports", "REPORTS", "REPORT", "Dashboard and quarterly sales reports"),
    ("REPORT_DOWNLOAD", "Download reports", "REPORTS", "DOWNLOAD", "Export reports as Excel or CSV files"),
    ("USER_READ", "View users", "USERS", "READ", "See users, their profiles and access rights"),
    ("USER_MANAGE", "Manage users", "USERS", "ADMIN", "Create staff accounts, assign profiles, disable or unlock users"),
]
MATRIX = {
    "ADMIN": [p[0] for p in PERMISSIONS],
    "STORE_MANAGER": ["CATALOG_READ", "CATALOG_WRITE", "ORDER_READ_ALL", "ORDER_MANAGE", "STOCK_READ", "STOCK_WRITE",
                      "REPORT_VIEW", "REPORT_DOWNLOAD", "USER_READ"],
    "WAREHOUSE_STAFF": ["CATALOG_READ", "ORDER_READ_ALL", "ORDER_MANAGE", "STOCK_READ", "STOCK_WRITE"],
    "CUSTOMER": ["CATALOG_READ", "ORDER_PLACE", "ORDER_READ_OWN"],
}
SETUP_TIME = START - timedelta(days=60)   # when the system was installed (reference data created)
STATES = {"Mumbai": "Maharashtra", "Pune": "Maharashtra", "Thane": "Maharashtra", "Navi Mumbai": "Maharashtra",
          "Bengaluru": "Karnataka", "Mysuru": "Karnataka", "Delhi": "Delhi", "Gurugram": "Haryana",
          "Noida": "Uttar Pradesh", "Lucknow": "Uttar Pradesh", "Chennai": "Tamil Nadu", "Coimbatore": "Tamil Nadu",
          "Hyderabad": "Telangana", "Kolkata": "West Bengal", "Ahmedabad": "Gujarat", "Surat": "Gujarat",
          "Jaipur": "Rajasthan", "Kochi": "Kerala"}

ADJUST_DOWN = ["Damaged in storage", "Expired / unsellable", "Stock count correction (missing)", "Damaged in transit"]
ADJUST_UP = ["Stock count correction (found extra)", "Supplier sent extra units"]


def pick_weighted(options, weights):
    return rng.choices(options, weights=weights, k=1)[0]


def rand_time(a: datetime, b: datetime) -> datetime:
    return a + timedelta(seconds=rng.uniform(0, (b - a).total_seconds()))


def season(t: datetime) -> float:
    """More shopping in festive months and evenings, so the reports have a shape."""
    month = {1: 0.9, 2: 0.85, 3: 0.95, 4: 0.9, 5: 0.9, 6: 0.85, 7: 0.9, 8: 1.05, 9: 1.1, 10: 1.5, 11: 1.45, 12: 1.3}[t.month]
    hour = 0.25 if t.hour < 8 else 1.3 if 18 <= t.hour <= 22 else 1.0
    return month * hour


def order_time(after: datetime) -> datetime:
    while True:   # rejection sampling with the season() weights
        t = rand_time(after, END - timedelta(minutes=1))
        if rng.random() * 1.95 < season(t):
            return t


def fmt(t):
    return t.strftime("%Y-%m-%d %H:%M:%S") if t else ""


# ----------------------------------------------------------------- build master data
def build_master():
    outlets = [{"outlet_id": i, "name": n, "city": c, "address": a} for i, (n, c, a) in enumerate(OUTLETS, 1)]
    outlet_by_name = {o["name"]: o["outlet_id"] for o in outlets}
    categories = [{"category_id": i, "name": n} for i, n in enumerate(CATEGORIES, 1)]
    cat_id = {c["name"]: c["category_id"] for c in categories}
    suppliers = [{"supplier_id": i, "name": n, "contact_email": e, "phone": p} for i, (n, e, p) in enumerate(SUPPLIERS, 1)]
    sup_id = {s["name"]: s["supplier_id"] for s in suppliers}

    products = []
    for i, (sku, name, cat, sup, price, desc) in enumerate(PRODUCTS, 1):
        if i <= 13 or rng.random() < 0.55:
            launch = START - timedelta(days=rng.randint(20, 40))            # sold from day one
        else:
            launch = rand_time(START + timedelta(days=30), datetime(2026, 6, 30))   # added to the range later
        withdrawn = rand_time(max(launch, datetime(2026, 1, 1)) + timedelta(days=60), END - timedelta(days=20)) \
            if sku in INACTIVE_SKUS else None
        products.append({
            "product_id": i, "sku": sku, "name": name, "description": desc, "price": price,
            "image_url": f"https://picsum.photos/seed/{sku}/400/300", "reorder_level": 10,
            "is_active": 0 if withdrawn else 1, "category_id": cat_id[cat],
            "supplier_id": sup_id[sup] if sup else "", "created_at": launch - timedelta(days=rng.randint(1, 5)),
            "updated_at": withdrawn or launch - timedelta(days=1),     # hidden from the shop = last change
            # not columns, used by the simulation:
            "_launch": launch, "_withdrawn": withdrawn,
            "_popularity": rng.uniform(0.3, 1.0) * (2.5 if price < 700 else 1.6 if price < 2000 else 1.0),
            "_supplier": sup or "the supplier",
        })
    return outlets, outlet_by_name, categories, suppliers, products


def build_users():
    """USERS rows; profile, address and home outlet are kept in _fields for the other tables."""
    def user(name, email, pw_hash, profile, created, **extra):
        return {"user_id": len(users) + 1, "full_name": name, "email": email, "password_hash": pw_hash,
                "account_status": "ACTIVE", "failed_login_count": 0, "locked_until": "", "last_login_at": "",
                "created_at": created, "updated_at": created, "_profile": profile, **extra}

    users = []
    users.append(user("Store Admin", "admin@inventory.com", ADMIN_HASH, "ADMIN", START - timedelta(days=45)))
    fixed = [("Demo Customer", "customer@inventory.com", "9876543210", "12 Hill Road, Bandra", "Mumbai", "400050"),
             ("Priya Sharma", "priya@example.com", "9876543211", "45 MG Road", "Pune", "411001"),
             ("Rahul Verma", "rahul@example.com", "9876543212", "8 Indiranagar", "Bengaluru", "560038"),
             ("Aisha Khan", "aisha@example.com", "9876543213", "22 Connaught Place", "Delhi", "110001")]
    emails = {"admin@inventory.com"} | {f[1] for f in fixed}
    phones = {f[2] for f in fixed}
    for name, email, phone, line, city, pin in fixed:
        users.append(user(name, email, CUSTOMER_HASH, "CUSTOMER", START - timedelta(days=rng.randint(5, 15)),
                          _phone=phone, _line=line, _city=city, _pincode=pin, _address=f"{line}, {city} - {pin}"))

    city_names = list(CITIES)
    city_weights = [CITIES[c][0] for c in city_names]
    while len(users) < 1 + N_CUSTOMERS:
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        base = f"{first}.{last}".lower().replace("'", "")
        email = f"{base}@{rng.choice(EMAIL_DOMAINS)}"
        while email in emails:
            email = f"{base}{rng.randint(1, 9999)}@{rng.choice(EMAIL_DOMAINS)}"
        emails.add(email)
        phone = str(rng.randint(6, 9)) + "".join(rng.choices("0123456789", k=9))
        while phone in phones:
            phone = str(rng.randint(6, 9)) + "".join(rng.choices("0123456789", k=9))
        phones.add(phone)
        city = pick_weighted(city_names, city_weights)
        _, areas, pin, _ = CITIES[city]
        flat = f"Flat {rng.randint(1, 20)}{rng.randint(0, 3):02d}, {rng.choice(BUILDINGS)}, " if rng.random() < 0.55 \
            else f"{rng.randint(1, 450)}, "
        line = f"{flat}{rng.choice(STREETS)}, {rng.choice(areas)}"
        pincode = f"{pin}{rng.randint(1, 99):03d}"
        users.append(user(f"{first} {last}", email, CUSTOMER_HASH, "CUSTOMER", rand_time(START, END - timedelta(days=2)),
                          _phone=phone, _line=line, _city=city, _pincode=pincode, _address=f"{line}, {city} - {pincode}"))
    # Two more staff accounts (password admin123)
    users.append(user("Inventory Manager", "manager@inventory.com", ADMIN_HASH, "STORE_MANAGER", START - timedelta(days=40)))
    users.append(user("Warehouse Supervisor", "warehouse@inventory.com", ADMIN_HASH, "WAREHOUSE_STAFF",
                      START - timedelta(days=40)))
    return users


def build_access(users, outlet_by_name):
    """PROFILES, PERMISSIONS, AUTHORIZATIONS (reference data), USER_PROFILES and CUSTOMER_PROFILES."""
    profiles = [{"profile_id": i, "profile_code": c, "profile_name": n, "description": d, "is_staff": s}
                for i, (c, n, d, s) in enumerate(PROFILES, 1)]
    profile_id = {p["profile_code"]: p["profile_id"] for p in profiles}
    permissions = [{"permission_id": i, "permission_code": c, "permission_name": n, "module": m, "access_type": a,
                    "description": d} for i, (c, n, m, a, d) in enumerate(PERMISSIONS, 1)]
    permission_id = {p["permission_code"]: p["permission_id"] for p in permissions}
    authorizations = [{"profile_id": profile_id[prof], "permission_id": permission_id[perm], "granted_at": SETUP_TIME,
                       "granted_by": ""}
                      for prof, perms in MATRIX.items() for perm in sorted(perms, key=permission_id.get)]
    admin = next(u["user_id"] for u in users if u["_profile"] == "ADMIN")
    user_profiles, customer_profiles = [], []
    for u in users:
        staff = u["_profile"] != "CUSTOMER"
        user_profiles.append({"user_id": u["user_id"], "profile_id": profile_id[u["_profile"]],
                              "assigned_at": u["created_at"],
                              "assigned_by": admin if staff and u["user_id"] != admin else ""})
        if not staff:
            customer_profiles.append({
                "customer_id": u["user_id"], "phone": u["_phone"], "address_line": u["_line"], "city": u["_city"],
                "state": STATES[u["_city"]], "pincode": u["_pincode"],
                "preferred_outlet_id": outlet_by_name[CITIES[u["_city"]][3]],
                "created_at": u["created_at"], "updated_at": u["created_at"]})
    return profiles, permissions, authorizations, user_profiles, customer_profiles


# ----------------------------------------------------------------- order plans
def plan_orders(users, products, outlet_by_name):
    """Decide every order's time, outlet, cart and fate. Stock is checked later, in time order."""
    n_outlets = len(OUTLETS)
    count_options = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    count_weights = [20, 32, 23, 12, 7, 3, 1.2, 0.8, 0.5, 0.3, 0.2]
    plans = []
    for u in users:
        if u["_profile"] != "CUSTOMER":
            continue
        n = rng.randint(5, 9) if u["user_id"] <= 5 else pick_weighted(count_options, count_weights)
        home = outlet_by_name[CITIES[u["_city"]][3]]
        for _ in range(n):
            t = order_time(max(u["created_at"] + timedelta(minutes=rng.randint(5, 600)), START))
            outlet = home if rng.random() < 0.88 else rng.randint(1, n_outlets)
            address = u["_address"] if rng.random() < 0.9 else \
                f"Office: {rng.randint(1, 30)}th Floor, {rng.choice(['Tech Park', 'Trade Centre', 'Business Bay', 'Corporate Tower'])}, " \
                f"{rng.choice(CITIES[u['_city']][1])}, {u['_city']}"
            plans.append({"t": t, "customer": u["user_id"], "outlet": outlet, "address": address})
    plans.sort(key=lambda p: p["t"])

    for p in plans:
        t = p["t"]
        sellable = [x for x in products if x["_launch"] < t and (x["_withdrawn"] is None or t < x["_withdrawn"])]
        lines = pick_weighted([1, 2, 3, 4, 5], [45, 30, 15, 7, 3])
        chosen = set()
        while len(chosen) < min(lines, len(sellable)):
            chosen.add(rng.choices(sellable, weights=[x["_popularity"] for x in sellable], k=1)[0]["product_id"])
        p["items"] = {pid: pick_weighted([1, 2, 3, 4, 5], [70, 20, 7, 2, 1]) for pid in sorted(chosen)}

        # fate of the order
        r = rng.random()
        p["failed_attempt"] = rng.random() < 0.06            # a declined payment before the final outcome
        p["method"] = pick_weighted(["UPI", "CARD", "NETBANKING"], [50, 35, 15])
        if r < 0.025:
            p["fate"] = "EXPIRED"                            # abandoned checkout, released after 30 min
            p["t_end"] = t + timedelta(minutes=rng.uniform(PAYMENT_TIMEOUT_MIN + 1, 180))
        elif r < 0.04:
            p["fate"] = "CANCELLED_UNPAID"                   # customer cancelled before paying
            p["t_end"] = t + timedelta(minutes=rng.uniform(2, PAYMENT_TIMEOUT_MIN - 2))
        else:
            p["t_pay"] = t + timedelta(minutes=rng.uniform(1, 15))
            if p["t_pay"] >= END:                            # ordered in the last few minutes
                p["t_pay"] = t + (END - t) / 2
            p["t_ship"] = p["t_pay"] + timedelta(hours=rng.uniform(4, 36))
            p["t_ofd"] = p["t_ship"] + timedelta(days=rng.uniform(1, 4))
            p["t_delivered"] = p["t_ofd"] + timedelta(hours=rng.uniform(2, 10))
            p["courier"] = rng.choice(COURIERS)
            if r < 0.07:
                p["fate"] = "CANCELLED_PAID"                 # paid, then cancelled before it shipped -> refund
                p["t_end"] = p["t_pay"] + (p["t_ship"] - p["t_pay"]) * rng.uniform(0.1, 0.9)
            elif r < 0.10:
                p["fate"] = "RETURNED"                       # shipped/delivered, then sent back -> restock + refund
                p["return_from"] = "DELIVERED" if rng.random() < 0.85 else "OUT_FOR_DELIVERY"
                base = p["t_delivered"] if p["return_from"] == "DELIVERED" else p["t_ofd"]
                p["t_end"] = base + timedelta(days=rng.uniform(0.5, 10))
            else:
                p["fate"] = "PAID"
        # An outcome that would happen after END hasn't happened yet: the order is simply paid.
        if p["fate"] in ("EXPIRED", "CANCELLED_UNPAID") and p["t_end"] >= END:
            p["fate"] = "PAID"
            p["t_pay"] = t + (END - t) / 2
            p["t_ship"] = p["t_ofd"] = p["t_delivered"] = END + timedelta(days=1)
            p["courier"] = rng.choice(COURIERS)
        if p["fate"] in ("CANCELLED_PAID", "RETURNED") and p["t_end"] >= END:
            p["fate"] = "PAID"
    return plans


# ----------------------------------------------------------------- simulation
def simulate(users, products, outlets, plans, outlet_by_name):
    admins = [u["user_id"] for u in users if "STOCK_WRITE" in MATRIX[u["_profile"]]]   # staff who may change stock
    warehouse = [u["user_id"] for u in users if u["_profile"] == "WAREHOUSE_STAFF"]
    prod = {p["product_id"]: p for p in products}
    outlet_name = {o["outlet_id"]: o["name"] for o in outlets}
    stock, last_change, inv_order = {}, {}, []
    movements, orders, items, payments, deliveries = [], [], [], [], []
    txn_refs = set()
    pending_restock = set()
    po_number = [1000]

    events, seq = [], [0]

    def push(t, kind, data):
        if t < END:
            seq[0] += 1
            heapq.heappush(events, (t, seq[0], kind, data))

    def move(t, pid, oid, change, mtype, user, order_id, note):
        key = (pid, oid)
        if key not in stock:
            stock[key] = 0
            inv_order.append(key)
        assert stock[key] + change >= 0, "stock would go negative"
        stock[key] += change
        last_change[key] = t
        movements.append({"movement_id": len(movements) + 1, "product_id": pid, "outlet_id": oid,
                          "qty_change": change, "movement_type": mtype, "note": note,
                          "order_id": order_id or "", "user_id": user or "", "created_at": t})

    def maybe_reorder(t, pid, oid):
        p = prod[pid]
        if stock[(pid, oid)] >= 40 or (pid, oid) in pending_restock:
            return
        if p["_withdrawn"] and t >= p["_withdrawn"] - timedelta(days=20):
            return   # being withdrawn: let it sell out
        pending_restock.add((pid, oid))
        richest = max((o for o in range(1, len(outlets) + 1) if o != oid), key=lambda o: stock.get((pid, o), 0))
        if stock.get((pid, richest), 0) > 160 and rng.random() < 0.3:
            push(t + timedelta(hours=rng.uniform(2, 24)), "transfer", (pid, richest, oid))
        else:
            push(t + timedelta(hours=rng.uniform(12, 72)), "restock", (pid, oid))

    # opening stock when each product is launched, at every outlet
    for p in products:
        for o in outlets:
            push(p["_launch"] + timedelta(minutes=o["outlet_id"]), "opening", (p["product_id"], o["outlet_id"]))
    for plan in plans:
        push(plan["t"], "place", plan)
    # weekly stock audits (small corrections)
    t = START + timedelta(days=7, hours=18)
    while t < END:
        for _ in range(rng.randint(2, 6)):
            push(t + timedelta(minutes=rng.randint(0, 120)), "adjust", None)
        t += timedelta(days=7)
    # the demo's low-stock items, one hour before END
    low_keys = set()
    for sku, oname in LOW_STOCK_DEMO:
        pid = next(p["product_id"] for p in products if p["sku"] == sku)
        low_keys.add((pid, outlet_by_name[oname]))
        push(END - timedelta(hours=1), "lowstock", (pid, outlet_by_name[oname]))

    while events:
        t, _, kind, data = heapq.heappop(events)
        if kind == "opening":
            pid, oid = data
            move(t, pid, oid, rng.randrange(60, 201, 5), "RESTOCK", admins[0], None, "Opening stock")
        elif kind == "restock":
            pid, oid = data
            pending_restock.discard(data)
            if data in low_keys and t >= END - timedelta(hours=1):
                continue   # keep the demo's low-stock items low
            po_number[0] += 1
            move(t, pid, oid, rng.randrange(80, 251, 10), "RESTOCK", rng.choice(admins), None,
                 f"PO-{po_number[0]} received from {prod[pid]['_supplier']}")
        elif kind == "transfer":
            pid, src, dst = data
            pending_restock.discard((pid, dst))
            if (pid, dst) in low_keys and t >= END - timedelta(hours=1):
                continue
            qty = min(rng.randrange(20, 61, 5), stock[(pid, src)] - 60)
            if qty > 0:
                note = f"Rebalancing: {outlet_name[src]} -> {outlet_name[dst]}"
                user = rng.choice(admins)
                move(t, pid, src, -qty, "TRANSFER_OUT", user, None, note)
                move(t, pid, dst, qty, "TRANSFER_IN", user, None, note)
            else:
                pending_restock.add((pid, dst))
                push(t + timedelta(hours=rng.uniform(12, 48)), "restock", (pid, dst))
        elif kind == "adjust":
            key = rng.choice(inv_order) if inv_order else None
            if key and stock[key] >= 5:
                if rng.random() < 0.8:
                    move(t, *key, -rng.randint(1, 3), "ADJUSTMENT", rng.choice(admins), None, rng.choice(ADJUST_DOWN))
                else:
                    move(t, *key, rng.randint(1, 2), "ADJUSTMENT", rng.choice(admins), None, rng.choice(ADJUST_UP))
                maybe_reorder(t, *key)
        elif kind == "lowstock":
            pid, oid = data
            if stock[(pid, oid)] != 4:
                move(t, pid, oid, 4 - stock[(pid, oid)], "ADJUSTMENT", admins[0], None, "Stock audit correction")
        elif kind == "place":
            plan = data
            oid = plan["outlet"]
            lines = {}
            for pid, qty in plan["items"].items():
                qty = min(qty, stock.get((pid, oid), 0))   # the customer can only buy what is on the shelf
                if qty > 0:
                    lines[pid] = qty
            if not lines:
                continue   # nothing available: the order is never created (place_order would reject it)
            order_id = len(orders) + 1
            plan["order_id"], plan["lines"] = order_id, lines
            total = 0
            for pid, qty in lines.items():   # sorted by product_id, like place_order
                move(t, pid, oid, -qty, "SALE", plan["customer"], order_id, f"Order #{order_id}")
                items.append({"order_item_id": len(items) + 1, "order_id": order_id, "product_id": pid,
                              "quantity": qty, "unit_price": prod[pid]["price"]})
                total += prod[pid]["price"] * qty
            plan["total"] = total
            orders.append(plan)
            for pid in lines:
                maybe_reorder(t, pid, oid)
            if plan["fate"] in ("EXPIRED", "CANCELLED_UNPAID", "CANCELLED_PAID", "RETURNED"):
                push(plan["t_end"], "undo", plan)
        elif kind == "undo":
            plan = data
            o, oid = plan["order_id"], plan["outlet"]
            if plan["fate"] == "EXPIRED":
                mtype, user, note = "CANCEL", None, f"Order #{o} not paid within {PAYMENT_TIMEOUT_MIN} minutes"
            elif plan["fate"] == "RETURNED":   # accepted back by warehouse staff
                mtype, user, note = "RETURN", warehouse[0], f"Order #{o} returned"
            else:
                mtype, user, note = "CANCEL", plan["customer"], f"Order #{o} cancelled"
            for pid, qty in plan["lines"].items():
                move(t, pid, oid, qty, mtype, user, o, note)

    # ---- orders, payments, deliveries from the final state of each plan
    order_rows = []
    for p in orders:
        o, fate = p["order_id"], p["fate"]
        status = {"PAID": "PAID", "RETURNED": "RETURNED"}.get(fate, "CANCELLED")
        order_row = {"order_id": o, "customer_id": p["customer"], "outlet_id": p["outlet"],
                     "order_status": status, "total_amount": p["total"],
                     "shipping_address": p["address"], "created_at": p["t"]}
        order_rows.append(order_row)
        method = p["method"] if (fate not in ("EXPIRED", "CANCELLED_UNPAID") or p["failed_attempt"]) else ""
        if fate in ("EXPIRED", "CANCELLED_UNPAID"):
            pay_status, txn, pay_time = "CANCELLED", "", p["t_end"]
        else:
            while True:
                txn = "TXN-" + "".join(rng.choices("0123456789ABCDEF", k=12))
                if txn not in txn_refs:
                    txn_refs.add(txn)
                    break
            pay_status = "SUCCESS" if fate == "PAID" else "REFUNDED"
            pay_time = p["t_pay"] if fate == "PAID" else p["t_end"]
        payments.append({"payment_id": o, "order_id": o, "amount": p["total"], "payment_method": method,
                         "payment_status": pay_status, "transaction_ref": txn, "updated_at": pay_time})

        courier = tracking = ""
        if fate in ("EXPIRED", "CANCELLED_UNPAID"):
            d_status, d_time = "NOT_SHIPPED", p["t"]
        elif fate == "CANCELLED_PAID":
            d_status, d_time = "PACKED", p["t_pay"]
        else:
            stages = [("PACKED", p["t_pay"]), ("SHIPPED", p["t_ship"]), ("OUT_FOR_DELIVERY", p["t_ofd"]),
                      ("DELIVERED", p["t_delivered"])]
            if fate == "RETURNED":
                stages = stages[:4 if p["return_from"] == "DELIVERED" else 3] + [("RETURNED", p["t_end"])]
            d_status, d_time = [s for s in stages if s[1] <= END][-1]
            if d_status != "PACKED":
                courier = p["courier"][0]
                tracking = f"{p['courier'][1]}{o:09d}"
        deliveries.append({"delivery_id": o, "order_id": o, "delivery_status": d_status, "courier": courier,
                           "tracking_number": tracking, "updated_at": d_time})
        # Triggers keep ORDERS.UPDATED_AT at the latest change of the order, its payment or its delivery.
        order_row["updated_at"] = max(p["t"], pay_time, d_time, p.get("t_end", p["t"]) if fate != "PAID" else p["t"])

    inventory = [{"inventory_id": i, "product_id": k[0], "outlet_id": k[1], "quantity": stock[k],
                  "updated_at": last_change[k]} for i, k in enumerate(inv_order, 1)]
    return order_rows, items, payments, deliveries, inventory, movements


# ----------------------------------------------------------------- write CSVs
COLUMNS = {
    "users": ["user_id", "full_name", "email", "password_hash", "account_status", "failed_login_count", "locked_until",
              "last_login_at", "created_at", "updated_at"],
    "outlets": ["outlet_id", "name", "city", "address"],
    "customer_profiles": ["customer_id", "phone", "address_line", "city", "state", "pincode", "preferred_outlet_id",
                          "created_at", "updated_at"],
    "profiles": ["profile_id", "profile_code", "profile_name", "description", "is_staff"],
    "permissions": ["permission_id", "permission_code", "permission_name", "module", "access_type", "description"],
    "authorizations": ["profile_id", "permission_id", "granted_at", "granted_by"],
    "user_profiles": ["user_id", "profile_id", "assigned_at", "assigned_by"],
    "categories": ["category_id", "name"],
    "suppliers": ["supplier_id", "name", "contact_email", "phone"],
    "products": ["product_id", "sku", "name", "description", "price", "image_url", "reorder_level", "is_active",
                 "category_id", "supplier_id", "created_at", "updated_at"],
    "inventory": ["inventory_id", "product_id", "outlet_id", "quantity", "updated_at"],
    "orders": ["order_id", "customer_id", "outlet_id", "order_status", "total_amount", "shipping_address", "created_at",
               "updated_at"],
    "order_items": ["order_item_id", "order_id", "product_id", "quantity", "unit_price"],
    "payments": ["payment_id", "order_id", "amount", "payment_method", "payment_status", "transaction_ref", "updated_at"],
    "deliveries": ["delivery_id", "order_id", "delivery_status", "courier", "tracking_number", "updated_at"],
    "stock_movements": ["movement_id", "product_id", "outlet_id", "qty_change", "movement_type", "note", "order_id",
                        "user_id", "created_at"],
}
FILE_ORDER = list(COLUMNS)   # parents before children: the order to load them in


def write(table, rows):
    cols = COLUMNS[table]
    with open(OUT / f"{table}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([c.upper() for c in cols])
        for r in rows:
            w.writerow([fmt(r[c]) if isinstance(r[c], datetime) else
                        (f"{r[c]:.2f}" if c in ("price", "total_amount", "unit_price", "amount") else r[c])
                        for c in cols])
    print(f"  {table + '.csv':<22} {len(rows):>8,} rows")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "app_users.csv").unlink(missing_ok=True)       # the users file of the earlier version
    outlets, outlet_by_name, categories, suppliers, products = build_master()
    users = build_users()
    profiles, permissions, authorizations, user_profiles, customer_profiles = build_access(users, outlet_by_name)
    plans = plan_orders(users, products, outlet_by_name)
    orders, items, payments, deliveries, inventory, movements = simulate(users, products, outlets, plans, outlet_by_name)
    # Last login: customers logged in to place their latest order; staff logged in today.
    last_order = {}
    for o in orders:
        last_order[o["customer_id"]] = o["created_at"]
    for u in users:
        u["last_login_at"] = (last_order.get(u["user_id"], "") if u["_profile"] == "CUSTOMER"
                              else END - timedelta(hours=rng.uniform(1, 8)))
    print(f"Writing {OUT.relative_to(ROOT)}/")
    tables = {"users": users, "outlets": outlets, "customer_profiles": customer_profiles, "profiles": profiles,
              "permissions": permissions, "authorizations": authorizations, "user_profiles": user_profiles,
              "categories": categories, "suppliers": suppliers, "products": products, "inventory": inventory,
              "orders": orders, "order_items": items, "payments": payments, "deliveries": deliveries,
              "stock_movements": movements}
    for table in FILE_ORDER:
        write(table, tables[table])


if __name__ == "__main__":
    main()
