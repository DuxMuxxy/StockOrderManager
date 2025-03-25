import os
import logging
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Database setup
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")

# Configure database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///inventory.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize app with the extension
db.init_app(app)

# Add context processors
@app.context_processor
def utility_processor():
    return {
        'now': datetime.now
    }

# Import routes after app is created to avoid circular imports
with app.app_context():
    # Import models to ensure tables are created
    from models import Product, Inventory, OrderPeriod, Order, OrderItem
    db.create_all()
    
    # Import utility functions
    from utils import get_current_inventory, get_current_order_period, get_orders_for_period, toggle_delivery_status

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/products')
def products():
    products_list = Product.query.all()
    return render_template('products.html', products=products_list)

@app.route('/products/add', methods=['POST'])
def add_product():
    name = request.form.get('name')
    description = request.form.get('description', '')
    
    if not name:
        flash('Product name is required', 'danger')
        return redirect(url_for('products'))
    
    # Check if product already exists
    existing = Product.query.filter_by(name=name).first()
    if existing:
        flash(f'A product with the name "{name}" already exists', 'danger')
        return redirect(url_for('products'))
    
    # Create new product
    product = Product(name=name, description=description)
    db.session.add(product)
    db.session.commit()
    
    flash(f'Product "{name}" added successfully', 'success')
    return redirect(url_for('products'))

@app.route('/products/update', methods=['POST'])
def update_product():
    product_id = request.form.get('editing_product_id', type=int)
    name = request.form.get('name')
    description = request.form.get('description', '')
    
    if not product_id or not name:
        flash('Invalid input data', 'danger')
        return redirect(url_for('products'))
    
    product = Product.query.get_or_404(product_id)
    
    # Check if name already exists for another product
    existing = Product.query.filter(Product.name == name, Product.id != product_id).first()
    if existing:
        flash(f'A product with the name "{name}" already exists', 'danger')
        return redirect(url_for('products'))
    
    product.name = name
    product.description = description
    db.session.commit()
    
    flash(f'Product "{name}" updated successfully', 'success')
    return redirect(url_for('products'))

@app.route('/products/<int:product_id>/delete', methods=['POST'])
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    # Delete associated inventory items
    Inventory.query.filter_by(product_id=product_id).delete()
    
    # Delete associated order items
    OrderItem.query.filter_by(product_id=product_id).delete()
    
    # Delete the product
    db.session.delete(product)
    db.session.commit()
    
    flash(f'Product "{product.name}" and all related inventory/order items have been deleted', 'success')
    return redirect(url_for('products'))

@app.route('/inventory')
def inventory():
    inventory_items = get_current_inventory()
    products = Product.query.all()
    return render_template('inventory.html', inventory=inventory_items, products=products)

@app.route('/inventory/update', methods=['POST'])
def update_inventory():
    product_id = request.form.get('product_id', type=int)
    quantity = request.form.get('quantity', type=int)
    
    if not product_id or quantity is None:
        flash('Invalid input data', 'danger')
        return redirect(url_for('inventory'))
    
    inventory_item = Inventory.query.filter_by(product_id=product_id).first()
    
    if inventory_item:
        inventory_item.quantity = quantity
    else:
        inventory_item = Inventory(product_id=product_id, quantity=quantity)
        db.session.add(inventory_item)
    
    db.session.commit()
    flash('Inventory updated successfully', 'success')
    return redirect(url_for('inventory'))

@app.route('/order_periods')
def order_periods():
    periods = OrderPeriod.query.order_by(OrderPeriod.year.desc(), OrderPeriod.month.desc()).all()
    current_period = get_current_order_period()
    
    return render_template('order_periods.html', periods=periods, current_period=current_period)

@app.route('/order_periods/create', methods=['POST'])
def create_order_period():
    month = request.form.get('month', type=int)
    year = request.form.get('year', type=int)
    
    if not month or not year or month < 1 or month > 12:
        flash('Invalid month or year', 'danger')
        return redirect(url_for('order_periods'))
    
    # Check if this period already exists
    existing = OrderPeriod.query.filter_by(month=month, year=year).first()
    if existing:
        flash('This order period already exists', 'danger')
        return redirect(url_for('order_periods'))
    
    # Close all currently open periods
    open_periods = OrderPeriod.query.filter_by(is_open=True).all()
    for period in open_periods:
        period.is_open = False
    
    # Create new period
    new_period = OrderPeriod(month=month, year=year, is_open=True)
    db.session.add(new_period)
    db.session.commit()
    
    flash(f'Order period for {month}/{year} created and opened', 'success')
    return redirect(url_for('order_periods'))

@app.route('/order_periods/<int:period_id>/toggle', methods=['POST'])
def toggle_order_period(period_id):
    period = OrderPeriod.query.get_or_404(period_id)
    
    if period.is_open:
        # Close this period
        period.is_open = False
        action = "closed"
    else:
        # Close all open periods
        open_periods = OrderPeriod.query.filter_by(is_open=True).all()
        for p in open_periods:
            p.is_open = False
        
        # Open this period
        period.is_open = True
        action = "opened"
    
    db.session.commit()
    flash(f'Order period {period.month}/{period.year} has been {action}', 'success')
    return redirect(url_for('order_periods'))

@app.route('/orders')
def orders():
    period_id = request.args.get('period_id', type=int)
    current_period = get_current_order_period()
    
    if period_id:
        period = OrderPeriod.query.get_or_404(period_id)
    else:
        period = current_period
    
    orders = []
    if period:
        orders = get_orders_for_period(period.id)
    
    periods = OrderPeriod.query.order_by(OrderPeriod.year.desc(), OrderPeriod.month.desc()).all()
    products = Product.query.all()
    
    return render_template('orders.html', 
                          orders=orders, 
                          period=period,
                          periods=periods, 
                          products=products, 
                          current_period=current_period)

@app.route('/orders/add', methods=['POST'])
def add_order():
    current_period = get_current_order_period()
    
    if not current_period:
        flash('No open order period available', 'danger')
        return redirect(url_for('orders'))
    
    user_name = request.form.get('user_name')
    user_id = request.form.get('user_id', user_name)  # Default to username if no ID
    product_ids = request.form.getlist('product_id[]')
    quantities = request.form.getlist('quantity[]')
    
    if not user_name or not product_ids or not quantities:
        flash('Missing required fields', 'danger')
        return redirect(url_for('orders'))
    
    # Check if user already has an order for this period
    existing_order = Order.query.filter_by(
        user_id=user_id, 
        order_period_id=current_period.id
    ).first()
    
    if existing_order:
        # Delete existing order items
        OrderItem.query.filter_by(order_id=existing_order.id).delete()
        order = existing_order
    else:
        # Create new order
        order = Order(
            user_id=user_id,
            user_name=user_name,
            order_period_id=current_period.id
        )
        db.session.add(order)
        db.session.flush()  # To get the order.id
    
    # Add order items
    for i in range(len(product_ids)):
        if i < len(quantities) and int(quantities[i]) > 0:
            item = OrderItem(
                order_id=order.id,
                product_id=int(product_ids[i]),
                quantity=int(quantities[i])
            )
            db.session.add(item)
    
    db.session.commit()
    flash('Order saved successfully', 'success')
    return redirect(url_for('orders'))

@app.route('/orders/<int:order_id>/delete', methods=['POST'])
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    current_period = get_current_order_period()
    
    if not current_period or order.order_period_id != current_period.id:
        flash('Can only delete orders from the current open period', 'danger')
        return redirect(url_for('orders'))
    
    # Delete order items first
    OrderItem.query.filter_by(order_id=order.id).delete()
    db.session.delete(order)
    db.session.commit()
    
    flash('Order deleted successfully', 'success')
    return redirect(url_for('orders'))

@app.route('/orders/<int:order_id>/toggle-delivery', methods=['POST'])
def toggle_order_delivery(order_id):
    order, error = toggle_delivery_status(order_id)
    
    if error:
        flash(error, 'danger')
    else:
        status = "Delivered" if order.is_delivered else "Not Delivered"
        flash(f'Order by {order.user_name} marked as {status}', 'success')
    
    # Redirect back to the orders page with the same period filter
    period_id = request.args.get('period_id')
    if period_id:
        return redirect(url_for('orders', period_id=period_id))
    else:
        return redirect(url_for('orders'))

# API endpoints
@app.route('/api/inventory', methods=['GET'])
def api_inventory():
    inventory_items = get_current_inventory()
    result = []
    
    for item in inventory_items:
        result.append({
            'product_id': item.product_id,
            'product_name': item.product.name,
            'quantity': item.quantity
        })
    
    return jsonify(result)

@app.route('/api/products', methods=['GET'])
def api_products():
    products = Product.query.all()
    result = []
    
    for product in products:
        result.append({
            'id': product.id,
            'name': product.name,
            'description': product.description
        })
    
    return jsonify(result)

@app.route('/api/order_periods', methods=['GET'])
def api_order_periods():
    periods = OrderPeriod.query.order_by(OrderPeriod.year.desc(), OrderPeriod.month.desc()).all()
    result = []
    
    for period in periods:
        result.append({
            'id': period.id,
            'month': period.month,
            'year': period.year,
            'is_open': period.is_open
        })
    
    return jsonify(result)

@app.route('/api/order_periods/current', methods=['GET'])
def api_current_order_period():
    period = get_current_order_period()
    
    if not period:
        return jsonify({"error": "No open order period found"}), 404
    
    return jsonify({
        'id': period.id,
        'month': period.month,
        'year': period.year,
        'is_open': period.is_open
    })

@app.route('/api/order_periods', methods=['POST'])
def api_create_order_period():
    data = request.json
    
    if not data or 'month' not in data or 'year' not in data:
        return jsonify({"error": "Missing required fields"}), 400
    
    month = data.get('month')
    year = data.get('year')
    
    if not isinstance(month, int) or not isinstance(year, int) or month < 1 or month > 12:
        return jsonify({"error": "Invalid month or year"}), 400
    
    # Check if this period already exists
    existing = OrderPeriod.query.filter_by(month=month, year=year).first()
    if existing:
        return jsonify({"error": "This order period already exists"}), 400
    
    # Close all currently open periods
    open_periods = OrderPeriod.query.filter_by(is_open=True).all()
    for period in open_periods:
        period.is_open = False
    
    # Create new period
    new_period = OrderPeriod(month=month, year=year, is_open=True)
    db.session.add(new_period)
    db.session.commit()
    
    return jsonify({
        'id': new_period.id,
        'month': new_period.month,
        'year': new_period.year,
        'is_open': new_period.is_open
    }), 201

@app.route('/api/order_periods/<int:period_id>/toggle', methods=['POST'])
def api_toggle_order_period(period_id):
    period = OrderPeriod.query.get_or_404(period_id)
    
    if period.is_open:
        # Close this period
        period.is_open = False
    else:
        # Close all open periods
        open_periods = OrderPeriod.query.filter_by(is_open=True).all()
        for p in open_periods:
            p.is_open = False
        
        # Open this period
        period.is_open = True
    
    db.session.commit()
    
    return jsonify({
        'id': period.id,
        'month': period.month,
        'year': period.year,
        'is_open': period.is_open
    })

@app.route('/api/orders', methods=['GET'])
def api_orders():
    period_id = request.args.get('period_id', type=int)
    
    if period_id:
        period = OrderPeriod.query.get_or_404(period_id)
    else:
        period = get_current_order_period()
        if not period:
            return jsonify({"error": "No open order period found"}), 404
    
    orders = get_orders_for_period(period.id)
    result = []
    
    for order in orders:
        items = []
        for item in order.items:
            items.append({
                'product_id': item.product_id,
                'product_name': item.product.name,
                'quantity': item.quantity
            })
        
        result.append({
            'id': order.id,
            'user_id': order.user_id,
            'user_name': order.user_name,
            'is_delivered': order.is_delivered,
            'items': items
        })
    
    return jsonify(result)

@app.route('/api/orders', methods=['POST'])
def api_add_order():
    data = request.json
    
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    current_period = get_current_order_period()
    
    if not current_period:
        return jsonify({"error": "No open order period available"}), 400
    
    user_name = data.get('user_name')
    user_id = data.get('user_id', user_name)  # Default to username if no ID
    items = data.get('items', [])
    
    if not user_name or not items:
        return jsonify({"error": "Missing required fields"}), 400
    
    # Check if user already has an order for this period
    existing_order = Order.query.filter_by(
        user_id=user_id, 
        order_period_id=current_period.id
    ).first()
    
    if existing_order:
        # Delete existing order items
        OrderItem.query.filter_by(order_id=existing_order.id).delete()
        order = existing_order
    else:
        # Create new order
        order = Order(
            user_id=user_id,
            user_name=user_name,
            order_period_id=current_period.id
        )
        db.session.add(order)
        db.session.flush()  # To get the order.id
    
    # Add order items
    for item in items:
        product_id = item.get('product_id')
        quantity = item.get('quantity')
        
        if product_id and quantity and quantity > 0:
            order_item = OrderItem(
                order_id=order.id,
                product_id=product_id,
                quantity=quantity
            )
            db.session.add(order_item)
    
    db.session.commit()
    
    return jsonify({
        'id': order.id,
        'user_id': order.user_id,
        'user_name': order.user_name,
        'is_delivered': order.is_delivered,
        'order_period_id': order.order_period_id
    }), 201

@app.route('/api/orders/<int:order_id>', methods=['DELETE'])
def api_delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    current_period = get_current_order_period()
    
    if not current_period or order.order_period_id != current_period.id:
        return jsonify({"error": "Can only delete orders from the current open period"}), 400
    
    # Delete order items first
    OrderItem.query.filter_by(order_id=order.id).delete()
    db.session.delete(order)
    db.session.commit()
    
    return jsonify({"success": True}), 200

@app.route('/api/orders/<int:order_id>/toggle-delivery', methods=['POST'])
def api_toggle_order_delivery(order_id):
    order, error = toggle_delivery_status(order_id)
    
    if error:
        return jsonify({"error": error}), 400
    
    return jsonify({
        'id': order.id,
        'user_id': order.user_id,
        'user_name': order.user_name,
        'is_delivered': order.is_delivered,
        'order_period_id': order.order_period_id
    })
