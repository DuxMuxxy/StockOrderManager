import os
import discord
from discord.ext import commands
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Create app context for database access
import app
from models import Product, Inventory, OrderPeriod, Order, OrderItem
from utils import (
    get_current_inventory, 
    get_current_order_period, 
    get_orders_for_period,
    add_order,
    delete_order,
    create_order_period,
    toggle_order_period,
    update_inventory
)

load_dotenv()

# Set up intents
intents = discord.Intents.default()
intents.message_content = True

# Create bot
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')

@bot.command(name='inventory', help='Show current inventory')
async def show_inventory(ctx):
    with app.app.app_context():
        inventory_items = get_current_inventory()
        
        if not inventory_items:
            await ctx.send("No inventory items found.")
            return
        
        embed = discord.Embed(
            title="Current Inventory",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        for item in inventory_items:
            embed.add_field(
                name=f"{item.product.name}",
                value=f"Quantity: {item.quantity}",
                inline=True
            )
        
        await ctx.send(embed=embed)

@bot.command(name='current_orders', help='Show orders for the current open month')
async def show_current_orders(ctx):
    with app.app.app_context():
        current_period = get_current_order_period()
        
        if not current_period:
            await ctx.send("No open order period available.")
            return
        
        orders = get_orders_for_period(current_period.id)
        
        if not orders:
            await ctx.send(f"No orders found for {current_period.month}/{current_period.year}.")
            return
        
        embed = discord.Embed(
            title=f"Orders for {current_period.month}/{current_period.year}",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        for order in orders:
            value = ""
            for item in order.items:
                value += f"{item.product.name}: {item.quantity}\n"
            
            embed.add_field(
                name=f"Order by {order.user_name}",
                value=value or "No items",
                inline=False
            )
        
        await ctx.send(embed=embed)

@bot.command(name='past_orders', help='Show orders for a past month (format: MM/YYYY)')
async def show_past_orders(ctx, period_str=None):
    if not period_str:
        await ctx.send("Please provide a month/year in MM/YYYY format.")
        return
    
    try:
        month, year = map(int, period_str.split('/'))
        if month < 1 or month > 12:
            await ctx.send("Month must be between 1 and 12.")
            return
    except ValueError:
        await ctx.send("Invalid format. Please use MM/YYYY format (e.g., 01/2023).")
        return
    
    with app.app.app_context():
        period = OrderPeriod.query.filter_by(month=month, year=year).first()
        
        if not period:
            await ctx.send(f"No order period found for {month}/{year}.")
            return
        
        orders = get_orders_for_period(period.id)
        
        if not orders:
            await ctx.send(f"No orders found for {month}/{year}.")
            return
        
        embed = discord.Embed(
            title=f"Orders for {month}/{year}",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        for order in orders:
            value = ""
            for item in order.items:
                value += f"{item.product.name}: {item.quantity}\n"
            
            embed.add_field(
                name=f"Order by {order.user_name}",
                value=value or "No items",
                inline=False
            )
        
        await ctx.send(embed=embed)

@bot.command(name='order', help='Place an order for the current month')
async def place_order(ctx):
    with app.app.app_context():
        current_period = get_current_order_period()
        
        if not current_period:
            await ctx.send("No open order period available for ordering.")
            return
        
        products = Product.query.all()
        
        if not products:
            await ctx.send("No products available for ordering.")
            return
        
        # Create a message with available products
        embed = discord.Embed(
            title=f"Available Products for {current_period.month}/{current_period.year}",
            description="Reply with the product numbers and quantities as:\n1:5 2:3 ...",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        for i, product in enumerate(products, 1):
            embed.add_field(
                name=f"{i}. {product.name}",
                value=product.description or "No description",
                inline=True
            )
        
        await ctx.send(embed=embed)
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
        
        try:
            response = await bot.wait_for('message', check=check, timeout=120.0)
            
            # Parse the response to get product IDs and quantities
            items = []
            parts = response.content.split()
            
            for part in parts:
                if ':' not in part:
                    continue
                
                try:
                    idx_str, qty_str = part.split(':')
                    idx = int(idx_str)
                    qty = int(qty_str)
                    
                    if idx < 1 or idx > len(products) or qty < 1:
                        continue
                    
                    product_id = products[idx-1].id
                    items.append({
                        'product_id': product_id,
                        'quantity': qty
                    })
                except ValueError:
                    continue
            
            if not items:
                await ctx.send("No valid items specified. Order not placed.")
                return
            
            # Add the order
            user_id = str(ctx.author.id)
            user_name = ctx.author.name
            
            order, error = add_order(user_id, user_name, items)
            
            if error:
                await ctx.send(f"Error: {error}")
                return
            
            # Confirm the order
            embed = discord.Embed(
                title="Order Placed Successfully",
                description=f"Your order for {current_period.month}/{current_period.year} has been recorded.",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            
            for item in order.items:
                embed.add_field(
                    name=item.product.name,
                    value=f"Quantity: {item.quantity}",
                    inline=True
                )
            
            await ctx.send(embed=embed)
            
        except asyncio.TimeoutError:
            await ctx.send("Order timed out. Please try again.")

@bot.command(name='cancel_order', help='Cancel your order for the current month')
async def cancel_order(ctx):
    with app.app.app_context():
        current_period = get_current_order_period()
        
        if not current_period:
            await ctx.send("No open order period available.")
            return
        
        user_id = str(ctx.author.id)
        
        order = Order.query.filter_by(
            user_id=user_id,
            order_period_id=current_period.id
        ).first()
        
        if not order:
            await ctx.send("You don't have an order for the current period.")
            return
        
        success, error = delete_order(order.id, user_id)
        
        if error:
            await ctx.send(f"Error: {error}")
            return
        
        await ctx.send(f"Your order for {current_period.month}/{current_period.year} has been cancelled.")

@bot.command(name='open_month', help='Open a new order month (format: MM/YYYY)')
@commands.has_permissions(administrator=True)
async def open_month(ctx, period_str=None):
    if not period_str:
        await ctx.send("Please provide a month/year in MM/YYYY format.")
        return
    
    try:
        month, year = map(int, period_str.split('/'))
        if month < 1 or month > 12:
            await ctx.send("Month must be between 1 and 12.")
            return
    except ValueError:
        await ctx.send("Invalid format. Please use MM/YYYY format (e.g., 01/2023).")
        return
    
    with app.app.app_context():
        period, error = create_order_period(month, year)
        
        if error:
            await ctx.send(f"Error: {error}")
            return
        
        await ctx.send(f"Order period for {month}/{year} has been opened for orders.")

@bot.command(name='toggle_month', help='Open/close an order month (format: MM/YYYY)')
@commands.has_permissions(administrator=True)
async def toggle_month(ctx, period_str=None):
    if not period_str:
        await ctx.send("Please provide a month/year in MM/YYYY format.")
        return
    
    try:
        month, year = map(int, period_str.split('/'))
        if month < 1 or month > 12:
            await ctx.send("Month must be between 1 and 12.")
            return
    except ValueError:
        await ctx.send("Invalid format. Please use MM/YYYY format (e.g., 01/2023).")
        return
    
    with app.app.app_context():
        period = OrderPeriod.query.filter_by(month=month, year=year).first()
        
        if not period:
            await ctx.send(f"No order period found for {month}/{year}.")
            return
        
        period, error = toggle_order_period(period.id)
        
        if error:
            await ctx.send(f"Error: {error}")
            return
        
        status = "opened" if period.is_open else "closed"
        await ctx.send(f"Order period for {month}/{year} has been {status}.")

@bot.command(name='update_stock', help='Update inventory (format: <product_id> <quantity>)')
@commands.has_permissions(administrator=True)
async def update_stock(ctx, product_id: int = None, quantity: int = None):
    if product_id is None or quantity is None:
        await ctx.send("Please provide both product ID and quantity.")
        return
    
    with app.app.app_context():
        inventory_item, error = update_inventory(product_id, quantity)
        
        if error:
            await ctx.send(f"Error: {error}")
            return
        
        await ctx.send(f"Inventory updated: {inventory_item.product.name} now has {quantity} units.")

@bot.command(name='products', help='List all available products')
async def list_products(ctx):
    with app.app.app_context():
        products = Product.query.all()
        
        if not products:
            await ctx.send("No products found.")
            return
        
        embed = discord.Embed(
            title="Available Products",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        for product in products:
            embed.add_field(
                name=f"{product.id}. {product.name}",
                value=product.description or "No description",
                inline=True
            )
        
        await ctx.send(embed=embed)

@bot.command(name='add_product', help='Add a new product (format: "name" "description")')
@commands.has_permissions(administrator=True)
async def add_product(ctx, name=None, *, description=None):
    if not name:
        await ctx.send("Please provide a product name.")
        return
    
    with app.app.app_context():
        # Check if product already exists
        existing = Product.query.filter_by(name=name).first()
        if existing:
            await ctx.send(f"A product with the name '{name}' already exists.")
            return
        
        # Create new product
        product = Product(name=name, description=description or "")
        app.db.session.add(product)
        app.db.session.commit()
        
        await ctx.send(f"Product '{name}' added successfully with ID {product.id}.")

# Run the bot
if __name__ == "__main__":
    # Get the token from environment variables
    token = os.environ.get("DISCORD_BOT_TOKEN")
    
    if not token:
        print("Error: No Discord bot token found. Set the DISCORD_BOT_TOKEN environment variable.")
    else:
        bot.run(token)
