from models import Product, Inventory, OrderPeriod, Order, OrderItem
from sqlalchemy import desc

def get_current_inventory():
    """
    Returns the current inventory for all products.
    """
    return Inventory.query.all()

def get_current_order_period():
    """
    Returns the currently open order period, or None if no period is open.
    """
    return OrderPeriod.query.filter_by(is_open=True).first()

def get_orders_for_period(period_id):
    """
    Returns all orders for a specific order period.
    """
    return Order.query.filter_by(order_period_id=period_id).all()

def add_order(user_id, user_name, items):
    """
    Adds or updates an order for the current order period.
    
    Args:
        user_id (str): Unique identifier for the user
        user_name (str): Display name for the user
        items (list): List of dicts with product_id and quantity
        
    Returns:
        Order: The created or updated order
        str: Error message if any
    """
    current_period = get_current_order_period()
    
    if not current_period:
        return None, "No open order period available"
    
    # Check if user already has an order for this period
    from app import db
    
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
    
    return order, None

def delete_order(order_id, user_id=None):
    """
    Deletes an order from the current order period.
    
    Args:
        order_id (int): ID of the order to delete
        user_id (str, optional): If provided, checks if order belongs to this user
        
    Returns:
        bool: True if order was deleted, False otherwise
        str: Error message if any
    """
    from app import db
    
    current_period = get_current_order_period()
    
    if not current_period:
        return False, "No open order period available"
    
    order_query = Order.query.filter_by(id=order_id, order_period_id=current_period.id)
    
    if user_id:
        order_query = order_query.filter_by(user_id=user_id)
    
    order = order_query.first()
    
    if not order:
        return False, "Order not found or not in current period"
    
    # Delete order items first
    OrderItem.query.filter_by(order_id=order.id).delete()
    db.session.delete(order)
    db.session.commit()
    
    return True, None

def create_order_period(month, year):
    """
    Creates a new order period and opens it.
    
    Args:
        month (int): Month (1-12)
        year (int): Year (e.g., 2023)
        
    Returns:
        OrderPeriod: The created order period
        str: Error message if any
    """
    from app import db
    
    if not month or not year or month < 1 or month > 12:
        return None, "Invalid month or year"
    
    # Check if this period already exists
    existing = OrderPeriod.query.filter_by(month=month, year=year).first()
    if existing:
        return None, "This order period already exists"
    
    # Close all currently open periods
    open_periods = OrderPeriod.query.filter_by(is_open=True).all()
    for period in open_periods:
        period.is_open = False
    
    # Create new period
    new_period = OrderPeriod(month=month, year=year, is_open=True)
    db.session.add(new_period)
    db.session.commit()
    
    return new_period, None

def toggle_order_period(period_id):
    """
    Toggles an order period between open and closed.
    
    Args:
        period_id (int): ID of the order period to toggle
        
    Returns:
        OrderPeriod: The toggled order period
        str: Error message if any
    """
    from app import db
    
    period = OrderPeriod.query.get(period_id)
    
    if not period:
        return None, "Order period not found"
    
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
    
    return period, None

def update_inventory(product_id, quantity):
    """
    Updates the inventory for a product.
    
    Args:
        product_id (int): ID of the product
        quantity (int): New quantity
        
    Returns:
        Inventory: The updated inventory item
        str: Error message if any
    """
    from app import db
    
    if quantity < 0:
        return None, "Quantity cannot be negative"
    
    # Check if product exists
    product = Product.query.get(product_id)
    if not product:
        return None, "Product not found"
    
    inventory_item = Inventory.query.filter_by(product_id=product_id).first()
    
    if inventory_item:
        inventory_item.quantity = quantity
    else:
        inventory_item = Inventory(product_id=product_id, quantity=quantity)
        db.session.add(inventory_item)
    
    db.session.commit()
    
    return inventory_item, None
