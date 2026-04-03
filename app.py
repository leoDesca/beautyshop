import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

# ── Database Configuration ───────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///beautyshop.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ── Models ───────────────────────────────────────────────────────────────────

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)  # 'lip' or 'hair'
    image_url = db.Column(db.String(300), nullable=True)
    in_stock = db.Column(db.Boolean, default=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_cart():
    return session.get("cart", {})

def save_cart(cart):
    session["cart"] = cart
    session.modified = True

def cart_count():
    return sum(item["quantity"] for item in get_cart().values())

def current_user():
    user_id = session.get("user_id")
    if user_id:
        return User.query.get(user_id)
    return None

app.jinja_env.globals["cart_count"] = cart_count
app.jinja_env.globals["current_user"] = current_user

# ── Auth Routes ───────────────────────────────────────────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user():
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("All fields are required.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        elif User.query.filter_by(username=username).first():
            flash("That username is already taken.", "error")
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            flash(f"Welcome, {user.username}! 💄", "success")
            return redirect(url_for("index"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            flash(f"Welcome back, {user.username}! 💋", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ── Customer Routes ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    lip_products = Product.query.filter_by(category="lip", in_stock=True).all()
    hair_products = Product.query.filter_by(category="hair", in_stock=True).all()
    return render_template("index.html", lip_products=lip_products, hair_products=hair_products)


@app.route("/cart")
def cart():
    cart = get_cart()
    cart_items = []
    total = 0
    for product_id, item in cart.items():
        product = Product.query.get(int(product_id))
        if product:
            subtotal = product.price * item["quantity"]
            total += subtotal
            cart_items.append({"product": product, "quantity": item["quantity"], "subtotal": subtotal})
    return render_template("cart.html", cart_items=cart_items, total=total)


@app.route("/cart/add/<int:product_id>", methods=["POST"])
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    cart = get_cart()
    key = str(product_id)
    if key in cart:
        cart[key]["quantity"] += 1
    else:
        cart[key] = {"quantity": 1, "name": product.name, "price": product.price}
    save_cart(cart)
    flash(f"{product.name} added to cart!", "success")
    return redirect(request.referrer or url_for("index"))


@app.route("/cart/update/<int:product_id>", methods=["POST"])
def update_cart(product_id):
    quantity = int(request.form.get("quantity", 1))
    cart = get_cart()
    key = str(product_id)
    if key in cart:
        if quantity <= 0:
            del cart[key]
        else:
            cart[key]["quantity"] = quantity
    save_cart(cart)
    return redirect(url_for("cart"))


@app.route("/cart/remove/<int:product_id>")
def remove_from_cart(product_id):
    cart = get_cart()
    key = str(product_id)
    if key in cart:
        del cart[key]
        save_cart(cart)
    flash("Item removed from cart.", "info")
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["POST"])
def checkout():
    session.pop("cart", None)
    flash("Thank you for your order! We will be in touch soon. 💄", "success")
    return redirect(url_for("index"))


# ── Admin Routes ──────────────────────────────────────────────────────────────

@app.route("/admin")
def admin_dashboard():
    user = current_user()
    if not user or not user.is_admin:
        flash("Admin access only.", "error")
        return redirect(url_for("login"))
    products = Product.query.order_by(Product.category, Product.name).all()
    return render_template("admin_dashboard.html", products=products)


@app.route("/admin/product/add", methods=["GET", "POST"])
def admin_add_product():
    user = current_user()
    if not user or not user.is_admin:
        return redirect(url_for("login"))
    if request.method == "POST":
        product = Product(
            name=request.form["name"],
            description=request.form["description"],
            price=float(request.form["price"]),
            category=request.form["category"],
            image_url=request.form.get("image_url", ""),
            in_stock=request.form.get("in_stock") == "on",
        )
        db.session.add(product)
        db.session.commit()
        flash(f"Product '{product.name}' added!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_product_form.html", product=None, action="Add")


@app.route("/admin/product/edit/<int:product_id>", methods=["GET", "POST"])
def admin_edit_product(product_id):
    user = current_user()
    if not user or not user.is_admin:
        return redirect(url_for("login"))
    product = Product.query.get_or_404(product_id)
    if request.method == "POST":
        product.name = request.form["name"]
        product.description = request.form["description"]
        product.price = float(request.form["price"])
        product.category = request.form["category"]
        product.image_url = request.form.get("image_url", "")
        product.in_stock = request.form.get("in_stock") == "on"
        db.session.commit()
        flash(f"Product '{product.name}' updated!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_product_form.html", product=product, action="Edit")


@app.route("/admin/product/delete/<int:product_id>", methods=["POST"])
def admin_delete_product(product_id):
    user = current_user()
    if not user or not user.is_admin:
        return redirect(url_for("login"))
    product = Product.query.get_or_404(product_id)
    name = product.name
    db.session.delete(product)
    db.session.commit()
    flash(f"Product '{name}' deleted.", "info")
    return redirect(url_for("admin_dashboard"))


# ── Seed Data ─────────────────────────────────────────────────────────────────

def seed_data():
    if Product.query.count() == 0:
        products = [
            Product(name="Velvet Rose Lipstick", description="A rich, creamy lipstick in a stunning rose shade. Long-lasting formula that keeps lips moisturized all day.", price=12.99, category="lip", image_url="https://images.unsplash.com/photo-1586495777744-4e6232bf7263?w=400"),
            Product(name="Nude Matte Lip Gloss", description="Smooth and lightweight lip gloss with a matte finish. Perfect for everyday wear.", price=8.99, category="lip", image_url="https://images.unsplash.com/photo-1631214524020-3c69b4a2b7d0?w=400"),
            Product(name="Berry Plum Lip Liner", description="Precise lip liner for defining and filling lips. Smudge-proof and long-wearing.", price=6.99, category="lip", image_url="https://images.unsplash.com/photo-1599305090598-fe179d501227?w=400"),
            Product(name="Glossy Pink Lip Oil", description="Nourishing lip oil with a beautiful glossy finish. Infused with vitamin E and jojoba oil.", price=10.99, category="lip", image_url="https://images.unsplash.com/photo-1617897903246-719242758050?w=400"),
            Product(name="Red Classic Lipstick", description="The timeless red that never goes out of style. Highly pigmented with a satin finish.", price=13.99, category="lip", image_url="https://images.unsplash.com/photo-1512496015851-a90fb38ba796?w=400"),
            Product(name="Argan Oil Hair Serum", description="Luxurious hair serum enriched with pure argan oil. Tames frizz, adds shine and softness.", price=15.99, category="hair", image_url="https://images.unsplash.com/photo-1527799820374-dcf8d9d4a388?w=400"),
            Product(name="Curl Defining Cream", description="Define and enhance your natural curls with this moisturizing cream. No crunch, no flaking.", price=14.99, category="hair", image_url="https://images.unsplash.com/photo-1522338242992-e1a54906a8da?w=400"),
            Product(name="Deep Moisture Hair Mask", description="Intensive conditioning treatment for dry and damaged hair. Restores shine and strength in minutes.", price=18.99, category="hair", image_url="https://images.unsplash.com/photo-1571781565036-d3f759be73e4?w=400"),
            Product(name="Scalp Nourishing Oil", description="Blend of natural oils to nourish the scalp and promote healthy hair growth.", price=16.99, category="hair", image_url="https://images.unsplash.com/photo-1608248597279-f99d160bfcbc?w=400"),
            Product(name="Heat Protect Spray", description="Protect your hair from heat damage up to 230 degrees. Lightweight formula that won't weigh hair down.", price=11.99, category="hair", image_url="https://images.unsplash.com/photo-1596755389378-c31d21fd1273?w=400"),
        ]
        for p in products:
            db.session.add(p)

    # Create default admin user
    if not User.query.filter_by(email="admin@lumiere.com").first():
        admin = User(username="admin", email="admin@lumiere.com", is_admin=True)
        admin.set_password(os.environ.get("ADMIN_PASSWORD", "admin123"))
        db.session.add(admin)

    db.session.commit()
    print("Database seeded.")


# ── Start ─────────────────────────────────────────────────────────────────────

# ── Initialize Database & Seed ─────────────────────────────
def initialize_database():
    """Create tables and seed data if not exists."""
    print("Connecting to database:", DATABASE_URL)
    db.create_all()  # Creates tables if they don't exist
    seed_data()      # Adds default products and admin user

# Run once when app starts
with app.app_context():
    initialize_database()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

