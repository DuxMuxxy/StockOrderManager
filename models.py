from app import db
from datetime import datetime

class Product(db.Model):
    """
    Represents a product that can be ordered.
    """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(500))
    
    def __repr__(self):
        return f"<Product {self.name}>"

class Inventory(db.Model):
    """
    Tracks the current inventory level for each product.
    """
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), primary_key=True)
    quantity = db.Column(db.Integer, default=0)
    
    # Relationships
    product = db.relationship('Product', backref='inventory_item')
    
    def __repr__(self):
        return f"<Inventory {self.product.name}: {self.quantity}>"

class OrderPeriod(db.Model):
    """
    Represents a month during which orders can be placed.
    Only one order period can be open at a time.
    """
    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)
    is_open = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    orders = db.relationship('Order', backref='order_period', cascade="all, delete-orphan")
    
    __table_args__ = (
        db.UniqueConstraint('month', 'year', name='unique_month_year'),
    )
    
    def __repr__(self):
        status = "Open" if self.is_open else "Closed"
        return f"<OrderPeriod {self.month}/{self.year} ({status})>"

class Order(db.Model):
    """
    Represents an order placed by a user for a specific order period.
    A user can only have one order per order period.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)  # Could be Discord ID or other identifier
    user_name = db.Column(db.String(100), nullable=False)  # Display name
    order_period_id = db.Column(db.Integer, db.ForeignKey('order_period.id'), nullable=False)
    is_delivered = db.Column(db.Boolean, default=False)  # Flag to track delivery status
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    items = db.relationship('OrderItem', backref='order', cascade="all, delete-orphan")
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'order_period_id', name='unique_user_period'),
    )
    
    def __repr__(self):
        delivery_status = "Delivered" if self.is_delivered else "Not Delivered"
        return f"<Order {self.id} by {self.user_name} ({delivery_status})>"

class OrderItem(db.Model):
    """
    Represents a single product within an order and its quantity.
    """
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)
    
    # Relationships
    product = db.relationship('Product')
    
    def __repr__(self):
        return f"<OrderItem {self.product.name}: {self.quantity}>"
