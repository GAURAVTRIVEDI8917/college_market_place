from flask import Flask, abort, render_template, request, redirect, url_for, session, flash
import sqlite3
import math
import os
import re
import secrets
import uuid
from functools import wraps
from urllib.parse import urlencode, urlparse
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("CAMPUSMART_SECRET_KEY") or os.urandom(32)

DATABASE = os.environ.get(
    "CAMPUSMART_DATABASE",
    os.path.join(app.root_path, "database.db")
)
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "images")
ADMIN_EMAIL = os.environ.get(
    "CAMPUSMART_ADMIN_EMAIL",
    "gtbhai501@gmail.com"
).strip().lower()
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
CATEGORIES = ("Books", "Electronics", "Clothing", "Furniture", "Sports", "Other")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


@app.context_processor
def inject_csrf_token():
    token = session.setdefault("_csrf_token", secrets.token_urlsafe(32))
    return {"csrf_token": token}


@app.before_request
def validate_csrf_token():
    if request.method == "POST":
        expected = session.get("_csrf_token", "")
        provided = request.form.get("_csrf_token", "")
        if not expected or not provided or not secrets.compare_digest(expected, provided):
            abort(400, description="Invalid or missing form security token.")


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_table():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            phone TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, product_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)

    user_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(users)")
    }
    if "is_admin" not in user_columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
        )
    if "is_active" not in user_columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"
        )
    if "phone" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            image TEXT NOT NULL,
            seller_phone TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'available'
                CHECK (status IN ('available', 'sold')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    product_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(products)")
    }
    if "status" not in product_columns:
        conn.execute(
            "ALTER TABLE products ADD COLUMN status TEXT NOT NULL DEFAULT 'available'"
        )
    if "seller_phone" not in product_columns:
        conn.execute(
            "ALTER TABLE products ADD COLUMN seller_phone TEXT NOT NULL DEFAULT ''"
        )
    conn.execute("""
        UPDATE products
        SET seller_phone = COALESCE(
            (SELECT phone FROM users WHERE users.id = products.user_id), ''
        )
        WHERE seller_phone = ''
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (product_id, user_id),
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            buyer_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            buyer_name TEXT NOT NULL,
            buyer_phone TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'confirmed', 'declined', 'cancelled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
            FOREIGN KEY (buyer_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_order_requests_seller
        ON order_requests(seller_id, status, created_at)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_order_requests_buyer
        ON order_requests(buyer_id, created_at)
    """)

    conn.execute(
        "UPDATE users SET is_admin = CASE WHEN lower(email) = ? THEN 1 ELSE 0 END",
        (ADMIN_EMAIL,)
    )

    conn.commit()
    conn.close()


@app.template_filter("whatsapp_url")
def whatsapp_url(phone, product_name):
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 8 or len(digits) > 15:
        return ""
    message = f"Hi, I am interested in your CampusMart listing: {product_name}"
    return f"https://wa.me/{digits}?{urlencode({'text': message})}"


def safe_return_url(target, fallback):
    parsed = urlparse(target or "")
    if parsed.scheme in {"http", "https"} and parsed.netloc == request.host:
        return target
    if (
        not parsed.scheme
        and not parsed.netloc
        and "\\" not in target
        and parsed.path.startswith("/")
        and not parsed.path.startswith("//")
    ):
        return target
    return fallback


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def valid_phone(phone):
    digits = re.sub(r"\D", "", phone)
    return (
        not phone
        or (
            re.fullmatch(r"\+?[0-9\s()-]{8,20}", phone) is not None
            and 8 <= len(digits) <= 15
        )
    )


def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first!")
            return redirect(url_for("login"))
        conn = get_db()
        user = conn.execute(
            "SELECT is_active FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()
        conn.close()
        if not user or not user["is_active"]:
            session.clear()
            flash("This account is currently disabled.")
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


def admin_required(function):
    @wraps(function)
    @login_required
    def wrapper(*args, **kwargs):
        conn = get_db()
        user = conn.execute(
            "SELECT is_admin FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()
        conn.close()

        if not user or not user["is_admin"]:
            flash("Administrator access is required.")
            return redirect(url_for("home"))
        return function(*args, **kwargs)
    return wrapper


def remove_product(product_id):
    conn = get_db()
    product = conn.execute(
        "SELECT image FROM products WHERE id = ?",
        (product_id,)
    ).fetchone()
    if not product:
        conn.close()
        return False

    conn.execute("DELETE FROM reviews WHERE product_id = ?", (product_id,))
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

    remove_product_image_if_unused(product["image"])
    return True


def remove_product_image_if_unused(image_path):
    conn = get_db()
    references = conn.execute(
        "SELECT COUNT(*) FROM products WHERE image = ?",
        (image_path,)
    ).fetchone()[0]
    conn.close()
    if references:
        return

    image_path = os.path.realpath(
        os.path.join(app.static_folder, image_path)
    )
    static_root = os.path.realpath(app.static_folder)
    if os.path.commonpath([static_root, image_path]) == static_root:
        if os.path.isfile(image_path):
            os.remove(image_path)


@app.route("/")
def home():
    conn = get_db()
    search = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    query = """
        SELECT products.*, users.name AS seller_name,
               users.email AS seller_email, users.phone AS seller_phone,
               COALESCE(AVG(reviews.rating), 0) AS average_rating,
               COUNT(reviews.id) AS review_count,
               CASE WHEN favorites.user_id IS NULL THEN 0 ELSE 1 END AS is_saved
        FROM products
        JOIN users ON products.user_id = users.id
        LEFT JOIN reviews ON reviews.product_id = products.id
        LEFT JOIN favorites ON favorites.product_id = products.id AND favorites.user_id = ?
        WHERE users.is_active = 1 AND products.status = 'available'
    """
    params = [session.get("user_id", -1)]
    if search:
        query += """
            AND (
                lower(products.name) LIKE lower(?)
                OR lower(products.category) LIKE lower(?)
                OR lower(products.description) LIKE lower(?)
            )
        """
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])
    if category:
        query += " AND products.category = ?"
        params.append(category)
    query += """
        GROUP BY products.id
        ORDER BY products.id DESC
    """
    products = conn.execute(query, params).fetchall()
    categories = conn.execute("""
        SELECT DISTINCT products.category
        FROM products
        JOIN users ON products.user_id = users.id
        WHERE users.is_active = 1 AND products.status = 'available'
        ORDER BY products.category
    """).fetchall()

    conn.close()

    return render_template(
        "index.html",
        products=products,
        categories=categories,
        search=search,
        selected_category=category
    )


@app.route("/product/<int:product_id>", methods=["GET", "POST"])
def product_detail(product_id):
    conn = get_db()
    product = conn.execute("""
        SELECT products.*, users.name AS seller_name, users.email AS seller_email,
               COALESCE(AVG(reviews.rating), 0) AS average_rating,
               COUNT(reviews.id) AS review_count,
               CASE WHEN favorites.user_id IS NULL THEN 0 ELSE 1 END AS is_saved
        FROM products
        JOIN users ON products.user_id = users.id
        LEFT JOIN reviews ON reviews.product_id = products.id
        LEFT JOIN favorites ON favorites.product_id = products.id
            AND favorites.user_id = ?
        WHERE products.id = ? AND users.is_active = 1
        GROUP BY products.id
    """, (session.get("user_id", -1), product_id)).fetchone()
    conn.close()

    if not product:
        flash("That product is no longer available.")
        return redirect(url_for("home"))

    viewer = None
    if "user_id" in session:
        conn = get_db()
        viewer = conn.execute(
            "SELECT name, phone FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()
        conn.close()

    if request.method == "POST":
        if "user_id" not in session:
            flash("Please login to leave a review.")
            return redirect(url_for("login"))
        conn = get_db()
        reviewer = conn.execute(
            "SELECT is_active FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()
        conn.close()
        if not reviewer or not reviewer["is_active"]:
            session.clear()
            flash("This account is currently disabled.")
            return redirect(url_for("login"))
        if session["user_id"] == product["user_id"]:
            flash("You cannot review your own listing.")
            return redirect(url_for("product_detail", product_id=product_id))
        if product["status"] != "available":
            flash("Reviews are closed for sold listings.")
            return redirect(url_for("product_detail", product_id=product_id))

        try:
            rating = int(request.form.get("rating", ""))
        except ValueError:
            rating = 0
        comment = request.form.get("comment", "").strip()

        if rating < 1 or rating > 5 or not comment or len(comment) > 1000:
            flash("Choose a 1-5 star rating and enter a review (up to 1000 characters).")
            return redirect(url_for("product_detail", product_id=product_id))

        conn = get_db()
        conn.execute("""
            INSERT INTO reviews (product_id, user_id, rating, comment)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(product_id, user_id) DO UPDATE SET
                rating = excluded.rating,
                comment = excluded.comment,
                created_at = CURRENT_TIMESTAMP
        """, (product_id, session["user_id"], rating, comment))
        conn.commit()
        conn.close()
        flash("Your review has been saved.")
        return redirect(url_for("product_detail", product_id=product_id))

    conn = get_db()
    reviews = conn.execute("""
        SELECT reviews.*, users.name AS reviewer_name
        FROM reviews
        JOIN users ON reviews.user_id = users.id
        WHERE reviews.product_id = ?
        ORDER BY reviews.created_at DESC
    """, (product_id,)).fetchall()
    conn.close()

    return render_template(
        "product.html",
        product=product,
        reviews=reviews,
        viewer=viewer
    )


@app.route("/product/<int:product_id>/order", methods=["POST"])
@login_required
def place_order_request(product_id):
    buyer_name = request.form.get("buyer_name", "").strip()
    buyer_phone = request.form.get("buyer_phone", "").strip()
    note = request.form.get("note", "").strip()

    if not buyer_name or len(buyer_name) > 100:
        flash("Enter your name (up to 100 characters) to request this order.")
        return redirect(url_for("product_detail", product_id=product_id))
    if not buyer_phone or not valid_phone(buyer_phone):
        flash("Enter a valid mobile number with country code to place an order request.")
        return redirect(url_for("product_detail", product_id=product_id))
    if len(note) > 500:
        flash("Order message must be 500 characters or fewer.")
        return redirect(url_for("product_detail", product_id=product_id))

    conn = get_db()
    conn.execute("""
        INSERT INTO order_requests
            (product_id, buyer_id, seller_id, buyer_name, buyer_phone, note)
        SELECT products.id, ?, products.user_id, ?, ?, ?
        FROM products
        WHERE products.id = ?
          AND products.status = 'available'
          AND products.seller_phone != ''
          AND products.user_id != ?
          AND NOT EXISTS (
              SELECT 1 FROM order_requests
              WHERE order_requests.product_id = products.id
                AND order_requests.buyer_id = ?
                AND order_requests.status = 'pending'
          )
    """, (
        session["user_id"], buyer_name, buyer_phone, note,
        product_id, session["user_id"], session["user_id"]
    ))
    created = conn.execute("SELECT changes()").fetchone()[0]

    if created:
        conn.commit()
        conn.close()
        flash("Order request sent! The seller will contact you to confirm payment and pickup.")
        return redirect(url_for("orders"))

    product = conn.execute(
        "SELECT user_id, status, seller_phone FROM products WHERE id = ?",
        (product_id,)
    ).fetchone()
    pending = conn.execute("""
        SELECT 1 FROM order_requests
        WHERE product_id = ? AND buyer_id = ? AND status = 'pending'
    """, (product_id, session["user_id"])).fetchone()
    conn.close()

    if not product:
        flash("This listing is no longer available.")
    elif product["user_id"] == session["user_id"]:
        flash("You cannot order your own listing.")
    elif not product["seller_phone"]:
        flash("The seller needs to add a mobile number before this item can be ordered.")
    elif product["status"] != "available":
        flash("This item has already been marked as sold.")
    elif pending:
        flash("You already have a pending request for this listing.")
    else:
        flash("Could not place the order request. Please try again.")
    return redirect(url_for("product_detail", product_id=product_id))


@app.route("/orders")
@login_required
def orders():
    conn = get_db()
    seller_orders = conn.execute("""
        SELECT order_requests.*, products.name AS product_name,
               products.price, products.image, products.status AS product_status,
               products.seller_phone
        FROM order_requests
        JOIN products ON products.id = order_requests.product_id
        WHERE order_requests.seller_id = ?
        ORDER BY order_requests.created_at DESC
    """, (session["user_id"],)).fetchall()
    buyer_orders = conn.execute("""
        SELECT order_requests.*, products.name AS product_name,
               products.price, products.image, users.name AS seller_name,
               products.seller_phone
        FROM order_requests
        JOIN products ON products.id = order_requests.product_id
        JOIN users ON users.id = order_requests.seller_id
        WHERE order_requests.buyer_id = ?
        ORDER BY order_requests.created_at DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    return render_template(
        "orders.html",
        seller_orders=seller_orders,
        buyer_orders=buyer_orders
    )


@app.route("/orders/<int:order_id>/status", methods=["POST"])
@login_required
def update_order_request(order_id):
    action = request.form.get("action", "")
    conn = get_db()

    if action == "cancel":
        cursor = conn.execute("""
            UPDATE order_requests
            SET status = 'cancelled'
            WHERE id = ? AND buyer_id = ? AND status = 'pending'
        """, (order_id, session["user_id"]))
        if cursor.rowcount:
            flash("Your order request was cancelled.")
        else:
            flash("This pending order request could not be cancelled.")
        conn.commit()
        conn.close()
        return redirect(url_for("orders"))

    if action not in {"confirm", "decline"}:
        conn.close()
        abort(400, description="Invalid order action.")

    conn.execute("BEGIN IMMEDIATE")
    order = conn.execute("""
        SELECT order_requests.product_id, order_requests.status,
               products.status AS product_status
        FROM order_requests
        JOIN products ON products.id = order_requests.product_id
        WHERE order_requests.id = ? AND order_requests.seller_id = ?
    """, (order_id, session["user_id"])).fetchone()

    if not order:
        conn.rollback()
        conn.close()
        flash("You can only manage order requests for your own listings.")
        return redirect(url_for("orders"))
    if order["status"] != "pending":
        conn.rollback()
        conn.close()
        flash("This order request has already been handled.")
        return redirect(url_for("orders"))

    if action == "decline":
        conn.execute(
            "UPDATE order_requests SET status = 'declined' WHERE id = ?",
            (order_id,)
        )
        conn.commit()
        conn.close()
        flash("Order request declined.")
        return redirect(url_for("orders"))

    if order["product_status"] != "available":
        conn.rollback()
        conn.close()
        flash("This item is no longer available, so the order cannot be confirmed.")
        return redirect(url_for("orders"))

    conn.execute(
        "UPDATE products SET status = 'sold' WHERE id = ? AND status = 'available'",
        (order["product_id"],)
    )
    if conn.execute("SELECT changes()").fetchone()[0] != 1:
        conn.rollback()
        conn.close()
        flash("This item is no longer available, so the order cannot be confirmed.")
        return redirect(url_for("orders"))
    conn.execute(
        "UPDATE order_requests SET status = 'confirmed' WHERE id = ?",
        (order_id,)
    )
    conn.execute("""
        UPDATE order_requests SET status = 'declined'
        WHERE product_id = ? AND status = 'pending' AND id != ?
    """, (order["product_id"], order_id))
    conn.commit()
    conn.close()
    flash("Order confirmed and listing marked sold. Contact the buyer to arrange payment and pickup.")
    return redirect(url_for("orders"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        phone = request.form.get("phone", "").strip()
        if not name or not email or not password:
            flash("All fields are required!")
            return redirect(url_for("register"))
        if len(name) > 100:
            flash("Name must be 100 characters or fewer.")
            return redirect(url_for("register"))

        if not valid_phone(phone):
            flash("Enter a valid phone number with country code for WhatsApp contact.")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters!")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        conn = get_db()

        try:
            conn.execute(
                "INSERT INTO users (name, email, password, is_admin, phone) VALUES (?, ?, ?, ?, ?)",
                (
                    name,
                    email,
                    hashed_password,
                    int(bool(ADMIN_EMAIL) and email == ADMIN_EMAIL),
                    phone or None
                )
            )
            conn.commit()
            flash("Registration successful! Please login.")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Email already registered!")

        finally:
            conn.close()

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_db()

        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        conn.close()

        if user and not user["is_active"]:
            flash("This account is currently disabled.")
        elif user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["is_admin"] = bool(user["is_admin"])

            flash("Login successful!")
            return redirect(safe_return_url(
                request.form.get("next"),
                url_for("home")
            ))
        else:
            flash("Invalid email or password!")

    return render_template("login.html")


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    conn = get_db()
    user = conn.execute(
        "SELECT name, email, phone, password FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()
    if not user:
        conn.close()
        session.clear()
        flash("Your account could not be found.")
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")

        if not name or len(name) > 100:
            conn.close()
            flash("Enter a name of 1-100 characters.")
            return redirect(url_for("account"))
        if not valid_phone(phone):
            conn.close()
            flash("Enter a valid phone number with country code for WhatsApp contact.")
            return redirect(url_for("account"))
        if current_password or new_password:
            if not current_password or not new_password:
                conn.close()
                flash("Enter both current and new password to change your password.")
                return redirect(url_for("account"))
            if not check_password_hash(user["password"], current_password):
                conn.close()
                flash("Current password is incorrect.")
                return redirect(url_for("account"))
            if len(new_password) < 8:
                conn.close()
                flash("New password must contain at least 8 characters.")
                return redirect(url_for("account"))
            conn.execute(
                "UPDATE users SET name = ?, phone = ?, password = ? WHERE id = ?",
                (
                    name,
                    phone or None,
                    generate_password_hash(new_password),
                    session["user_id"]
                )
            )
        else:
            conn.execute(
                "UPDATE users SET name = ?, phone = ? WHERE id = ?",
                (name, phone or None, session["user_id"])
            )
        conn.commit()
        conn.close()
        session["user_name"] = name
        flash("Your account details have been updated.")
        return redirect(url_for("account"))

    conn.close()
    return render_template("account.html", user=user)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        seller_phone = request.form.get("seller_phone", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        image = request.files.get("image")

        try:
            price = float(request.form.get("price", ""))
        except ValueError:
            flash("Please enter a valid price!")
            return redirect(url_for("sell"))

        if not name or not category or not description:
            flash("All fields are required!")
            return redirect(url_for("sell"))
        if not seller_phone or not valid_phone(seller_phone):
            flash("A valid seller mobile number with country code is required to list an item.")
            return redirect(url_for("sell"))
        if len(name) > 100 or len(description) > 2000 or category not in CATEGORIES:
            flash("Check the product name, category, and description length.")
            return redirect(url_for("sell"))

        if not math.isfinite(price) or price <= 0:
            flash("Price must be greater than zero!")
            return redirect(url_for("sell"))

        if not image or image.filename == "":
            flash("Please select a product image!")
            return redirect(url_for("sell"))

        if not allowed_file(image.filename):
            flash("Only PNG, JPG, JPEG and WEBP images are allowed!")
            return redirect(url_for("sell"))

        extension = image.filename.rsplit(".", 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{extension}"

        image.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_filename))

        image_path = "images/" + unique_filename

        conn = get_db()

        conn.execute("""
            INSERT INTO products
            (user_id, name, price, category, description, image, seller_phone)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            name,
            price,
            category,
            description,
            image_path,
            seller_phone
        ))
        conn.execute(
            "UPDATE users SET phone = ? WHERE id = ?",
            (seller_phone, session["user_id"])
        )

        conn.commit()
        conn.close()

        flash("Your product has been listed successfully! You can manage or delete it below.")
        return redirect(url_for("my_listings"))

    conn = get_db()
    user = conn.execute(
        "SELECT phone FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()
    conn.close()
    return render_template("sell.html", seller_phone=user["phone"] or "")


@app.route("/product/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def edit_product(product_id):
    conn = get_db()
    product = conn.execute(
        """SELECT products.*, users.phone AS account_phone
           FROM products JOIN users ON users.id = products.user_id
           WHERE products.id = ? AND products.user_id = ?""",
        (product_id, session["user_id"])
    ).fetchone()
    conn.close()
    if not product:
        flash("You can only edit your own listings.")
        return redirect(url_for("my_listings"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        seller_phone = request.form.get("seller_phone", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        image = request.files.get("image")

        try:
            price = float(request.form.get("price", ""))
        except ValueError:
            flash("Please enter a valid price!")
            return redirect(url_for("edit_product", product_id=product_id))

        if not name or not category or not description:
            flash("All fields are required!")
            return redirect(url_for("edit_product", product_id=product_id))
        if not seller_phone or not valid_phone(seller_phone):
            flash("A valid seller mobile number with country code is required to keep this listing active.")
            return redirect(url_for("edit_product", product_id=product_id))
        if len(name) > 100 or len(description) > 2000 or category not in CATEGORIES:
            flash("Check the product name, category, and description length.")
            return redirect(url_for("edit_product", product_id=product_id))

        if not math.isfinite(price) or price <= 0:
            flash("Price must be greater than zero!")
            return redirect(url_for("edit_product", product_id=product_id))

        image_path = product["image"]
        old_image_path = None
        if image and image.filename:
            if not allowed_file(image.filename):
                flash("Only PNG, JPG, JPEG and WEBP images are allowed!")
                return redirect(url_for("edit_product", product_id=product_id))

            old_image_path = image_path
            extension = image.filename.rsplit(".", 1)[1].lower()
            unique_filename = f"{uuid.uuid4().hex}.{extension}"
            image.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_filename))
            image_path = "images/" + unique_filename

        conn = get_db()
        conn.execute("""
            UPDATE products
            SET name = ?, price = ?, category = ?, description = ?, image = ?,
                seller_phone = ?
            WHERE id = ? AND user_id = ?
        """, (
            name, price, category, description, image_path, seller_phone,
            product_id, session["user_id"]
        ))
        conn.execute(
            "UPDATE users SET phone = ? WHERE id = ?",
            (seller_phone, session["user_id"])
        )
        conn.commit()
        conn.close()

        if old_image_path:
            remove_product_image_if_unused(old_image_path)

        flash("Your listing has been updated.")
        return redirect(url_for("my_listings"))

    return render_template("sell.html", product=product)


@app.route("/product/<int:product_id>/status", methods=["POST"])
@login_required
def toggle_product_status(product_id):
    conn = get_db()
    product = conn.execute(
        "SELECT status FROM products WHERE id = ? AND user_id = ?",
        (product_id, session["user_id"])
    ).fetchone()
    if product:
        status = "available" if product["status"] == "sold" else "sold"
        conn.execute(
            "UPDATE products SET status = ? WHERE id = ? AND user_id = ?",
            (status, product_id, session["user_id"])
        )
        conn.commit()
        flash("Listing marked available." if status == "available" else "Listing marked sold.")
    else:
        flash("You can only update your own listings.")
    conn.close()
    return redirect(url_for("my_listings"))


@app.route("/my-listings")
@login_required
def my_listings():
    conn = get_db()
    products = conn.execute("""
        SELECT products.*, COALESCE(AVG(reviews.rating), 0) AS average_rating,
               COUNT(reviews.id) AS review_count
        FROM products
        LEFT JOIN reviews ON reviews.product_id = products.id
        WHERE products.user_id = ?
        GROUP BY products.id
        ORDER BY products.id DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    return render_template("my_listings.html", products=products)


@app.route("/favorites")
@login_required
def favorites():
    conn = get_db()
    products = conn.execute("""
        SELECT products.*, users.name AS seller_name,
               COALESCE(AVG(reviews.rating), 0) AS average_rating,
               COUNT(reviews.id) AS review_count
        FROM favorites
        JOIN products ON products.id = favorites.product_id
        JOIN users ON users.id = products.user_id
        LEFT JOIN reviews ON reviews.product_id = products.id
        WHERE favorites.user_id = ? AND users.is_active = 1
        GROUP BY products.id
        ORDER BY favorites.created_at DESC
    """, (session["user_id"],)).fetchall()
    conn.close()
    return render_template("favorites.html", products=products)


@app.route("/product/<int:product_id>/favorite", methods=["POST"])
@login_required
def toggle_favorite(product_id):
    conn = get_db()
    product = conn.execute(
        "SELECT id, status FROM products WHERE id = ?",
        (product_id,)
    ).fetchone()
    if not product:
        flash("That product is no longer available.")
    else:
        existing = conn.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND product_id = ?",
            (session["user_id"], product_id)
        ).fetchone()
        if existing:
            conn.execute(
                "DELETE FROM favorites WHERE user_id = ? AND product_id = ?",
                (session["user_id"], product_id)
            )
            flash("Removed from saved products.")
        elif product["status"] != "available":
            flash("Sold products cannot be saved.")
        else:
            conn.execute(
                "INSERT INTO favorites (user_id, product_id) VALUES (?, ?)",
                (session["user_id"], product_id)
            )
            flash("Product saved to your favorites.")
        conn.commit()
    conn.close()
    fallback = url_for("product_detail", product_id=product_id)
    return redirect(safe_return_url(request.form.get("next"), fallback))


@app.route("/product/<int:product_id>/delete", methods=["POST"])
@login_required
def delete_own_product(product_id):
    conn = get_db()
    product = conn.execute(
        "SELECT user_id FROM products WHERE id = ?",
        (product_id,)
    ).fetchone()
    conn.close()

    if not product:
        flash("That product is no longer available.")
    elif product["user_id"] != session["user_id"]:
        flash("You can only remove your own listing.")
    elif remove_product(product_id):
        flash("Your listing has been removed.")
    return redirect(url_for("my_listings"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    products = conn.execute("""
        SELECT products.*, users.name AS seller_name,
               COUNT(reviews.id) AS review_count
        FROM products
        JOIN users ON products.user_id = users.id
        LEFT JOIN reviews ON reviews.product_id = products.id
        GROUP BY products.id
        ORDER BY products.id DESC
    """).fetchall()
    reviews = conn.execute("""
        SELECT reviews.*, products.name AS product_name,
               users.name AS reviewer_name
        FROM reviews
        JOIN products ON reviews.product_id = products.id
        JOIN users ON reviews.user_id = users.id
        ORDER BY reviews.created_at DESC
    """).fetchall()
    users = conn.execute("""
        SELECT id, name, email, is_admin, is_active
        FROM users
        ORDER BY name COLLATE NOCASE
    """).fetchall()
    conn.close()
    return render_template(
        "admin.html",
        products=products,
        reviews=reviews,
        users=users
    )


@app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def admin_delete_product(product_id):
    if remove_product(product_id):
        flash("Listing removed by administrator.")
    else:
        flash("That product is no longer available.")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reviews/<int:review_id>/delete", methods=["POST"])
@admin_required
def admin_delete_review(review_id):
    conn = get_db()
    result = conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()
    flash(
        "Review removed by administrator."
        if result.rowcount
        else "That review is no longer available."
    )
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_user(user_id):
    conn = get_db()
    user = conn.execute(
        "SELECT id, email, is_admin, is_active FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if not user:
        flash("That account no longer exists.")
    elif (
        user["id"] == session["user_id"]
        or user["is_admin"]
        or (ADMIN_EMAIL and user["email"].lower() == ADMIN_EMAIL)
    ):
        flash("Administrator accounts cannot be disabled here.")
    else:
        new_status = 0 if user["is_active"] else 1
        conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (new_status, user_id)
        )
        conn.commit()
        flash("Account suspended." if not new_status else "Account reactivated.")
    conn.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have logged out successfully.")
    return redirect(url_for("home"))


if __name__ == "__main__":

    create_table()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")