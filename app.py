from flask import Flask, render_template, request, redirect, url_for, jsonify
import psycopg2
import psycopg2.extras
from datetime import datetime
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
application = app

# --- Database Setup ---
def get_db():
    """Create a database connection"""
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn

def init_db():
    """Initialize database with tables and default items"""
    conn = get_db()
    c = conn.cursor()
    
    # Create tables[cite: 1]
    c.execute('''CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    price DECIMAL(10,2) NOT NULL,
                    active BOOLEAN DEFAULT TRUE
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
                    id SERIAL PRIMARY KEY,
                    customer_name VARCHAR(255) NOT NULL,
                    date TIMESTAMP NOT NULL,
                    total DECIMAL(10,2) NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS sale_items (
                    id SERIAL PRIMARY KEY,
                    sale_id INTEGER REFERENCES sales(id) ON DELETE CASCADE,
                    item_name VARCHAR(255),
                    quantity INTEGER,
                    price DECIMAL(10,2),
                    subtotal DECIMAL(10,2)
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
                    id SERIAL PRIMARY KEY,
                    description TEXT NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    category VARCHAR(255) NOT NULL,
                    date TIMESTAMP NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    
    # Insert default items only if table is empty[cite: 1]
    c.execute("SELECT COUNT(*) FROM items")
    if c.fetchone()['count'] == 0:
        items = [
            ("White Springtail", 120.00),
            ("Orange Springtail", 250.00),
            ("Agnara", 120.00),
            ("Porcellio Sevilla", 250.00)
        ]
        c.executemany("INSERT INTO items (name, price) VALUES (%s, %s)", items)
    
    conn.commit()
    conn.close()

# --- ROUTES ---
@app.route('/')
def dashboard():
    """Dashboard with statistics"""
    conn = get_db()
    c = conn.cursor()
    
    # Get statistics[cite: 1]
    c.execute("SELECT COALESCE(SUM(total), 0) FROM sales")
    total_revenue = c.fetchone()['coalesce']
    
    c.execute("SELECT COUNT(*) FROM sales")
    total_transactions = c.fetchone()['count']
    
    # Get total expenses[cite: 1]
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses")
    total_expenses = c.fetchone()['coalesce']
    
    # Calculate net profit[cite: 1]
    net_profit = total_revenue - total_expenses
    
    # Get recent sales (last 5)[cite: 1]
    c.execute("""SELECT id, customer_name, date, total 
                 FROM sales 
                 ORDER BY date DESC, id DESC 
                 LIMIT 5""")
    recent_sales = c.fetchall()
    
    # Get recent expenses (last 5)[cite: 1]
    c.execute("""SELECT id, description, amount, category, date 
                 FROM expenses 
                 ORDER BY date DESC, id DESC 
                 LIMIT 5""")
    recent_expenses = c.fetchall()
    
    # Get top selling items[cite: 1]
    c.execute("""SELECT si.item_name, i.id as item_id, SUM(si.quantity) as total_qty, SUM(si.subtotal) as total_sales
                 FROM sale_items si
                 LEFT JOIN items i ON si.item_name = i.name
                 GROUP BY si.item_name, i.id
                 ORDER BY total_qty DESC
                 LIMIT 5""")
    top_items = c.fetchall()
    
    # Get expense breakdown by category[cite: 1]
    c.execute("""SELECT category, SUM(amount) as total, 
                 STRING_AGG(id::text, ',') as expense_ids
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

# --- API ENDPOINTS FOR CHARTS ---
@app.route('/api/charts/monthly-sales')
def api_monthly_sales():
    """Get monthly sales data for chart"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""SELECT to_char(date, 'YYYY-MM') as month, 
                        SUM(total) as revenue,
                        COUNT(*) as transactions
                 FROM sales
                 GROUP BY to_char(date, 'YYYY-MM')
                 ORDER BY month DESC
                 LIMIT 12""")
    
    data = [dict(row) for row in c.fetchall()]
    data.reverse()  # Show oldest to newest[cite: 1]
    conn.close()
    
    return jsonify(data)

@app.route('/api/charts/item-sales')
def api_item_sales():
    """Get item sales breakdown"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""SELECT si.item_name, 
                        SUM(si.quantity) as total_qty,
                        SUM(si.subtotal) as total_sales
                 FROM sale_items si
                 GROUP BY si.item_name
                 ORDER BY total_sales DESC""")
    
    data = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify(data)

@app.route('/api/charts/expense-breakdown')
def api_expense_breakdown():
    """Get expense breakdown by category"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""SELECT category, SUM(amount) as total
                 FROM expenses
                 GROUP BY category
                 ORDER BY total DESC""")
    
    data = [dict(row) for row in c.fetchall()]
    conn.close()
    
    return jsonify(data)

@app.route('/api/charts/monthly-comparison')
def api_monthly_comparison():
    """Get monthly revenue vs expenses comparison"""
    conn = get_db()
    c = conn.cursor()
    
    # Get monthly sales[cite: 1]
    c.execute("""SELECT to_char(date, 'YYYY-MM') as month, SUM(total) as amount, 'Revenue' as type
                 FROM sales
                 GROUP BY to_char(date, 'YYYY-MM')""")
    sales_data = [dict(row) for row in c.fetchall()]
    
    # Get monthly expenses[cite: 1]
    c.execute("""SELECT to_char(date, 'YYYY-MM') as month, SUM(amount) as amount, 'Expenses' as type
                 FROM expenses
                 GROUP BY to_char(date, 'YYYY-MM')""")
    expense_data = [dict(row) for row in c.fetchall()]
    
    # Combine and organize data[cite: 1]
    all_months = set()
    for row in sales_data + expense_data:
        all_months.add(row['month'])
    
    result = []
    for month in sorted(all_months):
        revenue = next((r['amount'] for r in sales_data if r['month'] == month), 0)
        expenses = next((e['amount'] for e in expense_data if e['month'] == month), 0)
        result.append({
            'month': month,
            'revenue': revenue,
            'expenses': expenses,
            'profit': revenue - expenses
        })
    
    result.sort(key=lambda x: x['month'])
    result = result[-12:]  # Last 12 months[cite: 1]
    
    conn.close()
    return jsonify(result)

# --- SALES ROUTES ---
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

            total = 0
            sale_entries = []
            
            for item_id, qty in zip(item_ids, quantities):
                qty = int(qty)
                if qty > 0:
                    c.execute("SELECT name, price FROM items WHERE id=%s AND active=TRUE", (item_id,))
                    item = c.fetchone()
                    if item:
                        subtotal = item['price'] * qty
                        total += subtotal
                        sale_entries.append((item['name'], qty, item['price'], subtotal))

            if sale_entries:
                c.execute("INSERT INTO sales (customer_name, date, total, notes) VALUES (%s, %s, %s, %s) RETURNING id", 
                         (customer, date, total, notes))
                sale_id = c.fetchone()['id']

                c.executemany(
                    "INSERT INTO sale_items (sale_id, item_name, quantity, price, subtotal) VALUES (%s, %s, %s, %s, %s)",
                    [(sale_id, entry[0], entry[1], entry[2], entry[3]) for entry in sale_entries]
                )

                conn.commit()
                conn.close()
                
                return jsonify({
                    'success': True,
                    'sale_id': sale_id,
                    'customer_name': customer,
                    'date': date,
                    'notes': notes,
                    'items': [
                        {
                            'name': entry[0],
                            'quantity': entry[1],
                            'price': float(entry[2]),
                            'subtotal': float(entry[3])
                        } for entry in sale_entries
                    ],
                    'total': float(total)
                })
            else:
                conn.close()
                return jsonify({'success': False, 'error': 'Please add at least one item to the sale.'}), 400
        
        except Exception as e:
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    conn.close()
    return render_template('add_sale.html', 
                         items=get_active_items(),
                         today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/sales')
def view_sales():
    """View all sales"""
    conn = get_db()
    c = conn.cursor()
    
    search = request.args.get('search', '')
    
    query = """SELECT id, customer_name, date, total, notes 
               FROM sales 
               WHERE customer_name LIKE %s 
               ORDER BY date DESC, id DESC"""
    
    c.execute(query, (f'%{search}%',))
    sales = c.fetchall()

    expanded_sales = []
    for sale in sales:
        c.execute("""SELECT item_name as name, quantity, price, subtotal 
                     FROM sale_items 
                     WHERE sale_id=%s""", (sale['id'],))
        items = c.fetchall()
        
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
    
    c.execute("DELETE FROM sale_items WHERE sale_id=%s", (sale_id,))
    c.execute("DELETE FROM sales WHERE id=%s", (sale_id,))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('view_sales'))

@app.route('/sales/edit/<int:sale_id>', methods=['GET', 'POST'])
def edit_sale(sale_id):
    """Edit a sale"""
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM sales WHERE id=%s", (sale_id,))
    sale = c.fetchone()
    if not sale:
        conn.close()
        return "Sale not found", 404

    c.execute("SELECT * FROM sale_items WHERE sale_id=%s", (sale_id,))
    sale_items = [dict(row) for row in c.fetchall()]
    
    items = get_active_items()
    items_serializable = [
        {
            **item,
            'price': float(item['price'])
        } for item in items
    ]
    items_json = json.dumps(items_serializable)

    if request.method == 'POST':
        try:
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
                    c.execute("SELECT name, price FROM items WHERE id=%s", (item_id,))
                    item = c.fetchone()
                    if item:
                        subtotal = item['price'] * qty
                        total += subtotal
                        updated_items.append((item['name'], qty, item['price'], subtotal))

            if updated_items:
                c.execute("UPDATE sales SET customer_name=%s, date=%s, total=%s, notes=%s WHERE id=%s",
                          (customer, date, total, notes, sale_id))
                
                c.execute("DELETE FROM sale_items WHERE sale_id=%s", (sale_id,))
                
                c.executemany(
                    "INSERT INTO sale_items (sale_id, item_name, quantity, price, subtotal) VALUES (%s, %s, %s, %s, %s)",
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
    return render_template('edit_sale.html', 
                         sale=sale, 
                         sale_items=sale_items, 
                         items=items,
                         items_json=items_json)

# --- ITEMS ROUTES ---
@app.route('/items')
def manage_items():
    """Manage items"""
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
        c.execute("INSERT INTO items (name, price) VALUES (%s, %s)", (name, price))
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
        c.execute("UPDATE items SET name=%s, price=%s WHERE id=%s", (name, price, item_id))
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
    c.execute("UPDATE items SET active = NOT active WHERE id=%s", (item_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('manage_items'))

@app.route('/items/delete/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    """Delete item permanently"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM sale_items WHERE item_name = (SELECT name FROM items WHERE id=%s)", (item_id,))
        count = c.fetchone()['count']
        
        if count > 0:
            c.execute("UPDATE items SET active = FALSE WHERE id=%s", (item_id,))
        else:
            c.execute("DELETE FROM items WHERE id=%s", (item_id,))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error deleting item: {e}")
    
    return redirect(url_for('manage_items'))

# --- EXPENSE ROUTES ---
@app.route('/expenses')
def view_expenses():
    """View all expenses"""
    conn = get_db()
    c = conn.cursor()
    
    search = request.args.get('search', '')
    
    query = """SELECT id, description, amount, category, date, notes 
               FROM expenses 
               WHERE description LIKE %s OR category LIKE %s
               ORDER BY date DESC, id DESC"""
    
    c.execute(query, (f'%{search}%', f'%{search}%'))
    expenses = c.fetchall()
    
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses")
    total_expenses = c.fetchone()['coalesce']
    
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
                        VALUES (%s, %s, %s, %s, %s)""", 
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
    
    c.execute("SELECT * FROM expenses WHERE id=%s", (expense_id,))
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
                        SET description=%s, amount=%s, category=%s, date=%s, notes=%s 
                        WHERE id=%s""",
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
    c.execute("DELETE FROM expenses WHERE id=%s", (expense_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('view_expenses'))

@app.route('/expenses/delete-category/<category>', methods=['POST'])
def delete_category_expenses(category):
    """Delete all expenses in a category"""
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM expenses WHERE category=%s", (category,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('dashboard'))

@app.route('/sales/delete-item/<item_name>', methods=['POST'])
def delete_item_sales(item_name):
    """Delete all sales for a specific item"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT DISTINCT sale_id FROM sale_items WHERE item_name=%s", (item_name,))
    sale_ids = [row[0] for row in c.fetchall()]
    
    c.execute("DELETE FROM sale_items WHERE item_name=%s", (item_name,))
    
    for sale_id in sale_ids:
        c.execute("SELECT SUM(subtotal) FROM sale_items WHERE sale_id=%s", (sale_id,))
        new_total = c.fetchone()['sum']
        
        if new_total is None or new_total == 0:
            c.execute("DELETE FROM sales WHERE id=%s", (sale_id,))
        else:
            c.execute("UPDATE sales SET total=%s WHERE id=%s", (new_total, sale_id))
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('dashboard'))

# --- HELPER FUNCTIONS ---
def get_active_items():
    """Helper function to get active items"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM items WHERE active=TRUE ORDER BY name")
    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return items

# --- MAIN BLOCK ---
if __name__ == '__main__':
    # This only runs on your local machine, NOT on Vercel[cite: 1]
    init_db()
    app.run(debug=True)