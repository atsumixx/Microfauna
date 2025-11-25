from flask import Flask, render_template, request, redirect, url_for, jsonify
import sqlite3
from datetime import datetime
import json
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
    
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    description TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    date TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
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
    
    # Get total expenses
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses")
    total_expenses = c.fetchone()[0]
    
    # Calculate net profit
    net_profit = total_revenue - total_expenses
    
    # Get recent sales (last 5)
    c.execute("""SELECT id, customer_name, date, total 
                 FROM sales 
                 ORDER BY date DESC, id DESC 
                 LIMIT 5""")
    recent_sales = c.fetchall()
    
    # Get recent expenses (last 5)
    c.execute("""SELECT id, description, amount, category, date 
                 FROM expenses 
                 ORDER BY date DESC, id DESC 
                 LIMIT 5""")
    recent_expenses = c.fetchall()
    
    # Get top selling items
    c.execute("""SELECT si.item_name, i.id as item_id, SUM(si.quantity) as total_qty, SUM(si.subtotal) as total_sales
                 FROM sale_items si
                 LEFT JOIN items i ON si.item_name = i.name
                 GROUP BY si.item_name
                 ORDER BY total_qty DESC
                 LIMIT 5""")
    top_items = c.fetchall()
    
    # Get expense breakdown by category
    c.execute("""SELECT category, SUM(amount) as total, 
                 GROUP_CONCAT(id) as expense_ids
                 FROM expenses
                 GROUP BY category
                 ORDER BY total DESC
                 LIMIT 5""")
    expense_breakdown = c.fetchall()
    
    conn.close()
    
    return render_template('dashboard.html', 
                         revenue=total_revenue,
                         transactions=total_transactions,
                         expenses=total_expenses,
                         net_profit=net_profit,
                         recent_sales=recent_sales,
                         recent_expenses=recent_expenses,
                         top_items=top_items,
                         expense_breakdown=expense_breakdown)

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

# --- EDIT SALE ROUTE (FIXED) ---
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
    
    # Get all items (active and inactive) for dropdown
    items = get_active_items()
    
    # Convert items to JSON for JavaScript - THIS WAS MISSING
    items_json = json.dumps(items)

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
                    c.execute("SELECT name, price FROM items WHERE id=?", (item_id,))
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
                return render_template('edit_sale.html', 
                                     sale=sale, 
                                     sale_items=sale_items, 
                                     items=items,
                                     items_json=items_json,
                                     error="Please add at least one item.")
        except Exception as e:
            conn.close()
            return render_template('edit_sale.html', 
                                 sale=sale, 
                                 sale_items=sale_items, 
                                 items=items,
                                 items_json=items_json,
                                 error=f"Error updating sale: {str(e)}")

    conn.close()
    # FIXED: Now passing items_json to template
    return render_template('edit_sale.html', 
                         sale=sale, 
                         sale_items=sale_items, 
                         items=items,
                         items_json=items_json)

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

# --- EXPENSES ROUTES ---
@app.route('/expenses')
def view_expenses():
    """View all expenses"""
    conn = get_db()
    c = conn.cursor()
    
    # Get filter parameters
    search = request.args.get('search', '')
    
    # Build query
    query = """SELECT id, description, amount, category, date, notes 
               FROM expenses 
               WHERE description LIKE ? OR category LIKE ?
               ORDER BY date DESC, id DESC"""
    
    c.execute(query, (f'%{search}%', f'%{search}%'))
    expenses = c.fetchall()
    
    # Calculate total expenses
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses")
    total_expenses = c.fetchone()[0]
    
    conn.close()
    return render_template('view_expenses.html', 
                         expenses=[dict(exp) for exp in expenses], 
                         search=search,
                         total_expenses=total_expenses)

@app.route('/expenses/add', methods=['GET', 'POST'])
def add_expense():
    """Add new expense"""
    if request.method == 'POST':
        try:
            description = request.form['description'].strip()
            amount = float(request.form['amount'])
            category = request.form['category'].strip()
            date = request.form['date'] or datetime.now().strftime('%Y-%m-%d')
            notes = request.form.get('notes', '').strip()
            
            conn = get_db()
            c = conn.cursor()
            c.execute("""INSERT INTO expenses (description, amount, category, date, notes) 
                        VALUES (?, ?, ?, ?, ?)""", 
                     (description, amount, category, date, notes))
            conn.commit()
            conn.close()
            
            return redirect(url_for('view_expenses'))
        except Exception as e:
            return render_template('add_expense.html', 
                                 error=f"Error adding expense: {str(e)}",
                                 today=datetime.now().strftime('%Y-%m-%d'))
    
    return render_template('add_expense.html', 
                         today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/expenses/edit/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    """Edit an expense"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT * FROM expenses WHERE id=?", (expense_id,))
    expense = c.fetchone()
    
    if not expense:
        conn.close()
        return "Expense not found", 404
    
    if request.method == 'POST':
        try:
            description = request.form['description'].strip()
            amount = float(request.form['amount'])
            category = request.form['category'].strip()
            date = request.form['date']
            notes = request.form.get('notes', '').strip()
            
            c.execute("""UPDATE expenses 
                        SET description=?, amount=?, category=?, date=?, notes=? 
                        WHERE id=?""",
                     (description, amount, category, date, notes, expense_id))
            conn.commit()
            conn.close()
            
            return redirect(url_for('view_expenses'))
        except Exception as e:
            conn.close()
            return render_template('edit_expense.html', 
                                 expense=expense,
                                 error=f"Error updating expense: {str(e)}")
    
    conn.close()
    return render_template('edit_expense.html', expense=expense)

@app.route('/expenses/delete/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    """Delete an expense"""
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('view_expenses'))

@app.route('/expenses/delete-category/<category>', methods=['POST'])
def delete_category_expenses(category):
    """Delete all expenses in a category"""
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM expenses WHERE category=?", (category,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('dashboard'))

@app.route('/sales/delete-item/<item_name>', methods=['POST'])
def delete_item_sales(item_name):
    """Delete all sales for a specific item"""
    conn = get_db()
    c = conn.cursor()
    
    # Get all sale_ids that contain this item
    c.execute("SELECT DISTINCT sale_id FROM sale_items WHERE item_name=?", (item_name,))
    sale_ids = [row[0] for row in c.fetchall()]
    
    # Delete the sale_items for this item
    c.execute("DELETE FROM sale_items WHERE item_name=?", (item_name,))
    
    # For each affected sale, recalculate the total
    for sale_id in sale_ids:
        c.execute("SELECT SUM(subtotal) FROM sale_items WHERE sale_id=?", (sale_id,))
        new_total = c.fetchone()[0]
        
        if new_total is None or new_total == 0:
            # If no items left, delete the entire sale
            c.execute("DELETE FROM sales WHERE id=?", (sale_id,))
        else:
            # Update the sale total
            c.execute("UPDATE sales SET total=? WHERE id=?", (new_total, sale_id))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True)