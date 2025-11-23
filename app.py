from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)

# --- Database Setup ---
def get_db():
    """Create a database connection"""
    conn = sqlite3.connect('sales.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with tables and default items"""
    conn = get_db()
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    price REAL NOT NULL,
                    active INTEGER DEFAULT 1
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_name TEXT NOT NULL,
                    date TEXT NOT NULL,
                    total REAL NOT NULL,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sale_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_id INTEGER,
                    item_name TEXT,
                    quantity INTEGER,
                    price REAL,
                    subtotal REAL,
                    FOREIGN KEY (sale_id) REFERENCES sales(id) ON DELETE CASCADE
                )''')
    
    # Insert default items only if table is empty
    c.execute("SELECT COUNT(*) FROM items")
    if c.fetchone()[0] == 0:
        items = [
            ("White Springtail", 120.00),
            ("Orange Springtail", 250.00),
            ("Agnara", 120.00),
            ("Porcellio Sevilla", 250.00)
        ]
        c.executemany("INSERT INTO items (name, price) VALUES (?, ?)", items)
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

# --- ROUTES ---
@app.route('/')
def dashboard():
    """Dashboard with statistics"""
    conn = get_db()
    c = conn.cursor()
    
    # Get statistics
    c.execute("SELECT COALESCE(SUM(total), 0) FROM sales")
    total_revenue = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM sales")
    total_transactions = c.fetchone()[0]
    
    # Get recent sales (last 5)
    c.execute("""SELECT id, customer_name, date, total 
                 FROM sales 
                 ORDER BY date DESC, id DESC 
                 LIMIT 5""")
    recent_sales = c.fetchall()
    
    # Get top selling items
    c.execute("""SELECT item_name, SUM(quantity) as total_qty, SUM(subtotal) as total_sales
                 FROM sale_items
                 GROUP BY item_name
                 ORDER BY total_qty DESC
                 LIMIT 5""")
    top_items = c.fetchall()
    
    conn.close()
    
    return render_template('dashboard.html', 
                         revenue=total_revenue,
                         transactions=total_transactions,
                         recent_sales=recent_sales,
                         top_items=top_items)

@app.route('/add-sale', methods=['GET', 'POST'])
def add_sale():
    """Add new sale"""
    conn = get_db()
    c = conn.cursor()
    
    if request.method == 'POST':
        try:
            customer = request.form['customer_name'].strip()
            date = request.form['date'] or datetime.now().strftime('%Y-%m-%d')
            notes = request.form.get('notes', '').strip()
            item_ids = request.form.getlist('item_id')
            quantities = request.form.getlist('quantity')

            # Calculate total and prepare sale entries
            total = 0
            sale_entries = []
            
            for item_id, qty in zip(item_ids, quantities):
                qty = int(qty)
                if qty > 0:
                    c.execute("SELECT name, price FROM items WHERE id=? AND active=1", (item_id,))
                    item = c.fetchone()
                    if item:
                        subtotal = item['price'] * qty
                        total += subtotal
                        sale_entries.append((item['name'], qty, item['price'], subtotal))

            # Only insert if there are items
            if sale_entries:
                # Insert sale
                c.execute("INSERT INTO sales (customer_name, date, total, notes) VALUES (?, ?, ?, ?)", 
                         (customer, date, total, notes))
                sale_id = c.lastrowid

                # Insert sale items
                c.executemany(
                    "INSERT INTO sale_items (sale_id, item_name, quantity, price, subtotal) VALUES (?, ?, ?, ?, ?)",
                    [(sale_id, entry[0], entry[1], entry[2], entry[3]) for entry in sale_entries]
                )

                conn.commit()
                conn.close()
                return redirect(url_for('dashboard'))
            else:
                conn.close()
                return render_template('add_sale.html', 
                                     items=get_active_items(), 
                                     error="Please add at least one item to the sale.")
        
        except Exception as e:
            conn.close()
            return render_template('add_sale.html', 
                                 items=get_active_items(), 
                                 error=f"Error adding sale: {str(e)}")

    conn.close()
    return render_template('add_sale.html', 
                         items=get_active_items(),
                         today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/sales')
def view_sales():
    """View all sales"""
    conn = get_db()
    c = conn.cursor()
    
    # Get filter parameters
    search = request.args.get('search', '')
    
    # Build query
    query = """SELECT id, customer_name, date, total, notes 
               FROM sales 
               WHERE customer_name LIKE ? 
               ORDER BY date DESC, id DESC"""
    
    c.execute(query, (f'%{search}%',))
    sales = c.fetchall()

    # Get items for each sale
    expanded_sales = []
    for sale in sales:
        c.execute("""SELECT item_name as name, quantity, price, subtotal 
                     FROM sale_items 
                     WHERE sale_id=?""", (sale['id'],))
        items = c.fetchall()
        
        # Flatten the structure to match template expectations
        expanded_sales.append({
            'id': sale['id'],
            'customer': sale['customer_name'],
            'date': sale['date'],
            'total': sale['total'],
            'notes': sale['notes'],
            'items': [dict(item) for item in items]
        })

    conn.close()
    return render_template('view_sales.html', sales=expanded_sales, search=search)

@app.route('/sales/delete/<int:sale_id>', methods=['POST'])
def delete_sale(sale_id):
    """Delete a sale"""
    conn = get_db()
    c = conn.cursor()
    
    # Delete sale items first
    c.execute("DELETE FROM sale_items WHERE sale_id=?", (sale_id,))
    # Delete sale
    c.execute("DELETE FROM sales WHERE id=?", (sale_id,))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('view_sales'))

# --- EDIT SALE ROUTE ---
@app.route('/sales/edit/<int:sale_id>', methods=['GET', 'POST'])
def edit_sale(sale_id):
    """Edit a sale"""
    conn = get_db()
    c = conn.cursor()

    # Fetch sale
    c.execute("SELECT * FROM sales WHERE id=?", (sale_id,))
    sale = c.fetchone()
    if not sale:
        conn.close()
        return "Sale not found", 404

    # Fetch sale items
    c.execute("SELECT * FROM sale_items WHERE sale_id=?", (sale_id,))
    sale_items = [dict(row) for row in c.fetchall()]

    if request.method == 'POST':
        try:
            # Update sale info
            customer = request.form['customer_name'].strip()
            date = request.form['date']
            notes = request.form.get('notes', '').strip()
            
            item_ids = request.form.getlist('item_id')
            quantities = request.form.getlist('quantity')

            total = 0
            updated_items = []

            for item_id, qty in zip(item_ids, quantities):
                qty = int(qty)
                if qty > 0:
                    c.execute("SELECT name, price FROM items WHERE id=? AND active=1", (item_id,))
                    item = c.fetchone()
                    if item:
                        subtotal = item['price'] * qty
                        total += subtotal
                        updated_items.append((item['name'], qty, item['price'], subtotal))

            if updated_items:
                # Update sale
                c.execute("UPDATE sales SET customer_name=?, date=?, total=?, notes=? WHERE id=?",
                          (customer, date, total, notes, sale_id))
                
                # Delete old sale items
                c.execute("DELETE FROM sale_items WHERE sale_id=?", (sale_id,))
                
                # Insert updated items
                c.executemany(
                    "INSERT INTO sale_items (sale_id, item_name, quantity, price, subtotal) VALUES (?, ?, ?, ?, ?)",
                    [(sale_id, item[0], item[1], item[2], item[3]) for item in updated_items]
                )

                conn.commit()
                conn.close()
                return redirect(url_for('view_sales'))
            else:
                conn.close()
                return render_template('edit_sale.html', sale=sale, sale_items=sale_items, items=get_active_items(),
                                       error="Please add at least one item.")
        except Exception as e:
            conn.close()
            return render_template('edit_sale.html', sale=sale, sale_items=sale_items, items=get_active_items(),
                                   error=f"Error updating sale: {str(e)}")

    conn.close()
    return render_template('edit_sale.html', sale=sale, sale_items=sale_items, items=get_active_items())

# --- ITEMS ROUTES ---
@app.route('/items')
def manage_items():
    """Manage items (view, add, edit)"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM items ORDER BY name")
    items = c.fetchall()
    conn.close()
    
    return render_template('manage_items.html', items=[dict(item) for item in items])

@app.route('/items/add', methods=['POST'])
def add_item():
    """Add new item"""
    try:
        name = request.form['name'].strip()
        price = float(request.form['price'])
        
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO items (name, price) VALUES (?, ?)", (name, price))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error adding item: {e}")
    
    return redirect(url_for('manage_items'))

@app.route('/items/edit/<int:item_id>', methods=['POST'])
def edit_item(item_id):
    """Edit item"""
    try:
        name = request.form['name'].strip()
        price = float(request.form['price'])
        
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE items SET name=?, price=? WHERE id=?", (name, price, item_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error editing item: {e}")
    
    return redirect(url_for('manage_items'))

@app.route('/items/toggle/<int:item_id>', methods=['POST'])
def toggle_item(item_id):
    """Toggle item active status"""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE items SET active = 1 - active WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('manage_items'))

@app.route('/items/delete/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    """Delete item permanently"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Check if item is used in any sales
        c.execute("SELECT COUNT(*) FROM sale_items WHERE item_name = (SELECT name FROM items WHERE id=?)", (item_id,))
        count = c.fetchone()[0]
        
        if count > 0:
            # Don't delete, just deactivate
            c.execute("UPDATE items SET active = 0 WHERE id=?", (item_id,))
        else:
            # Safe to delete
            c.execute("DELETE FROM items WHERE id=?", (item_id,))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error deleting item: {e}")
    
    return redirect(url_for('manage_items'))

@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics"""
    conn = get_db()
    c = conn.cursor()
    
    # Monthly revenue
    c.execute("""SELECT strftime('%Y-%m', date) as month, SUM(total) as revenue
                 FROM sales
                 GROUP BY month
                 ORDER BY month DESC
                 LIMIT 12""")
    monthly_revenue = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    return jsonify(monthly_revenue)

def get_active_items():
    """Helper function to get active items"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM items WHERE active=1 ORDER BY name")
    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return items

if __name__ == '__main__':
    app.run(debug=True)
