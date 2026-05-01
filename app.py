from flask import Flask, render_template, request, redirect, url_for, jsonify, make_response
import psycopg2
import psycopg2.extras
from datetime import datetime
import json
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
def get_db():
    raw_uri = os.environ.get('DATABASE_URL')
    if not raw_uri:
        raise RuntimeError("DATABASE_URL not found in Environment Variables!")
    if raw_uri.startswith("postgres://"):
        raw_uri = raw_uri.replace("postgres://", "postgresql://", 1)
    conn = psycopg2.connect(raw_uri, sslmode='require')
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

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
                    discount DECIMAL(10,2) DEFAULT 0,
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

    # Add discount column if it doesn't exist (migration-safe)
    c.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='sales' AND column_name='discount'
            ) THEN
                ALTER TABLE sales ADD COLUMN discount DECIMAL(10,2) DEFAULT 0;
            END IF;
        END $$;
    """)

    # Fix items sequence if needed
    c.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='items' AND column_name='id'
                AND column_default LIKE 'nextval%'
            ) THEN
                CREATE SEQUENCE IF NOT EXISTS items_id_seq;
                ALTER TABLE items ALTER COLUMN id SET DEFAULT nextval('items_id_seq');
                PERFORM setval('items_id_seq', COALESCE((SELECT MAX(id) FROM items), 0) + 1);
            END IF;
        END $$;
    """)

    # Seed default items if empty
    c.execute("SELECT COUNT(*) FROM items")
    if c.fetchone()['count'] == 0:
        items = [
            ("White Springtail", 120.00),
            ("Orange Springtail", 250.00),
            ("Agnara", 120.00),
            ("Porcellio Sevilla", 250.00)
        ]
        c.executemany("INSERT INTO items (name, price, active) VALUES (%s, %s, TRUE)", items)

    conn.commit()
    conn.close()


try:
    init_db()
    print("Database initialized successfully.")
except Exception as e:
    print(f"WARNING: Startup DB init skipped: {e}")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def get_active_items():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM items WHERE active=TRUE ORDER BY name")
    items = [dict(row) for row in c.fetchall()]
    conn.close()
    return items


def get_sale_data(sale_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM sales WHERE id=%s", (sale_id,))
    sale = c.fetchone()
    if not sale:
        conn.close()
        return None
    c.execute("SELECT * FROM sale_items WHERE sale_id=%s", (sale_id,))
    items = [dict(row) for row in c.fetchall()]
    conn.close()
    discount = float(sale.get('discount') or 0)
    subtotal_sum = sum(float(i['subtotal']) for i in items)
    return {
        'sale_id': sale['id'],
        'customer_name': sale['customer_name'],
        'date': str(sale['date']),
        'notes': sale['notes'] or '',
        'discount': discount,
        'subtotal': subtotal_sum,
        'total': float(sale['total']),
        'items': [
            {
                'name': i['item_name'],
                'quantity': i['quantity'],
                'price': float(i['price']),
                'subtotal': float(i['subtotal'])
            } for i in items
        ]
    }


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
@app.route('/')
def dashboard():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COALESCE(SUM(total), 0) FROM sales")
    total_revenue = c.fetchone()['coalesce']

    c.execute("SELECT COUNT(*) FROM sales")
    total_transactions = c.fetchone()['count']

    c.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses")
    total_expenses = c.fetchone()['coalesce']

    net_profit = total_revenue - total_expenses

    c.execute("""SELECT id, customer_name, date, total
                 FROM sales ORDER BY date DESC, id DESC LIMIT 5""")
    recent_sales = c.fetchall()

    c.execute("""SELECT id, description, amount, category, date
                 FROM expenses ORDER BY date DESC, id DESC LIMIT 5""")
    recent_expenses = c.fetchall()

    c.execute("""SELECT si.item_name, i.id as item_id,
                        SUM(si.quantity) as total_qty, SUM(si.subtotal) as total_sales
                 FROM sale_items si
                 LEFT JOIN items i ON si.item_name = i.name
                 GROUP BY si.item_name, i.id
                 ORDER BY total_qty DESC LIMIT 5""")
    top_items = c.fetchall()

    c.execute("""SELECT category, SUM(amount) as total,
                        STRING_AGG(id::text, ',') as expense_ids
                 FROM expenses
                 GROUP BY category ORDER BY total DESC LIMIT 5""")
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


# ─────────────────────────────────────────────
# CHART / ANALYTICS APIs
# ─────────────────────────────────────────────
@app.route('/api/charts/monthly-sales')
def api_monthly_sales():
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT to_char(date, 'YYYY-MM') as month,
                        SUM(total) as revenue, COUNT(*) as transactions
                 FROM sales GROUP BY to_char(date, 'YYYY-MM')
                 ORDER BY month DESC LIMIT 12""")
    data = [dict(row) for row in c.fetchall()]
    data.reverse()
    conn.close()
    return jsonify(data)


@app.route('/api/charts/item-sales')
def api_item_sales():
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT si.item_name, SUM(si.quantity) as total_qty, SUM(si.subtotal) as total_sales
                 FROM sale_items si GROUP BY si.item_name ORDER BY total_sales DESC""")
    data = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(data)


@app.route('/api/charts/expense-breakdown')
def api_expense_breakdown():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT category, SUM(amount) as total FROM expenses GROUP BY category ORDER BY total DESC")
    data = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(data)


@app.route('/api/charts/monthly-comparison')
def api_monthly_comparison():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT to_char(date, 'YYYY-MM') as month, SUM(total) as amount FROM sales GROUP BY to_char(date, 'YYYY-MM')")
    sales_data = [dict(row) for row in c.fetchall()]
    c.execute("SELECT to_char(date, 'YYYY-MM') as month, SUM(amount) as amount FROM expenses GROUP BY to_char(date, 'YYYY-MM')")
    expense_data = [dict(row) for row in c.fetchall()]
    all_months = set(r['month'] for r in sales_data + expense_data)
    result = []
    for month in sorted(all_months):
        revenue  = next((r['amount'] for r in sales_data   if r['month'] == month), 0)
        expenses = next((e['amount'] for e in expense_data if e['month'] == month), 0)
        result.append({'month': month, 'revenue': revenue, 'expenses': expenses, 'profit': revenue - expenses})
    conn.close()
    return jsonify(result[-12:])


@app.route('/api/analytics/daily')
def api_analytics_daily():
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT to_char(date, 'YYYY-MM-DD') as day,
                        SUM(total) as revenue, COUNT(*) as transactions
                 FROM sales WHERE date >= NOW() - INTERVAL '30 days'
                 GROUP BY to_char(date, 'YYYY-MM-DD') ORDER BY day""")
    data = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(data)


@app.route('/api/analytics/weekly')
def api_analytics_weekly():
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT to_char(date_trunc('week', date), 'YYYY-MM-DD') as week_start,
                        SUM(total) as revenue, COUNT(*) as transactions
                 FROM sales WHERE date >= NOW() - INTERVAL '12 weeks'
                 GROUP BY date_trunc('week', date) ORDER BY week_start""")
    data = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(data)


@app.route('/api/analytics/monthly')
def api_analytics_monthly():
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT to_char(date, 'YYYY-MM') as month,
                        SUM(total) as revenue, COUNT(*) as transactions
                 FROM sales WHERE date >= NOW() - INTERVAL '12 months'
                 GROUP BY to_char(date, 'YYYY-MM') ORDER BY month""")
    data = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(data)


@app.route('/api/analytics/yearly')
def api_analytics_yearly():
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT to_char(date, 'YYYY') as year,
                        SUM(total) as revenue, COUNT(*) as transactions
                 FROM sales GROUP BY to_char(date, 'YYYY') ORDER BY year""")
    data = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(data)


# ─────────────────────────────────────────────
# RECEIPT
# ─────────────────────────────────────────────
@app.route('/sales/<int:sale_id>/receipt')
def view_receipt(sale_id):
    data = get_sale_data(sale_id)
    if not data:
        return jsonify({'error': 'Sale not found'}), 404
    return jsonify(data)


@app.route('/sales/<int:sale_id>/receipt/download')
def download_receipt(sale_id):
    data = get_sale_data(sale_id)
    if not data:
        return "Sale not found", 404

    lines = []
    lines.append("=" * 40)
    lines.append("       MICROFAUNA SALES RECEIPT")
    lines.append("=" * 40)
    lines.append(f"Receipt #: {data['sale_id']}")
    lines.append(f"Customer : {data['customer_name']}")
    lines.append(f"Date     : {data['date']}")
    if data['notes']:
        lines.append(f"Notes    : {data['notes']}")
    lines.append("-" * 40)
    lines.append(f"{'ITEM':<20} {'QTY':>4} {'PRICE':>7} {'TOTAL':>7}")
    lines.append("-" * 40)
    for item in data['items']:
        lines.append(f"{item['name']:<20} {item['quantity']:>4} P{item['price']:>6.2f} P{item['subtotal']:>6.2f}")
    lines.append("-" * 40)
    lines.append(f"{'SUBTOTAL':>33} P{data['subtotal']:>6.2f}")
    if data['discount'] > 0:
        lines.append(f"{'DISCOUNT':>33} P{data['discount']:>6.2f}")
    lines.append(f"{'TOTAL':>33} P{data['total']:>6.2f}")
    lines.append("=" * 40)
    lines.append("    Thank you for your purchase!")
    lines.append("=" * 40)

    content = "\n".join(lines)
    response = make_response(content)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    response.headers['Content-Disposition'] = \
        f'attachment; filename=receipt_{sale_id}_{data["customer_name"].replace(" ", "_")}.txt'
    return response


# ─────────────────────────────────────────────
# SALES ROUTES
# ─────────────────────────────────────────────
@app.route('/add-sale', methods=['GET', 'POST'])
def add_sale():
    conn = get_db()
    c = conn.cursor()

    if request.method == 'POST':
        try:
            customer   = request.form['customer_name'].strip()
            date       = request.form['date'] or datetime.now().strftime('%Y-%m-%d')
            notes      = request.form.get('notes', '').strip()
            discount   = float(request.form.get('discount', 0) or 0)
            item_ids   = request.form.getlist('item_id')
            quantities = request.form.getlist('quantity')

            subtotal_sum = 0
            sale_entries = []

            for item_id, qty in zip(item_ids, quantities):
                qty = int(qty)
                if qty > 0:
                    c.execute("SELECT name, price FROM items WHERE id=%s AND active=TRUE", (item_id,))
                    item = c.fetchone()
                    if item:
                        subtotal = float(item['price']) * qty
                        subtotal_sum += subtotal
                        sale_entries.append((item['name'], qty, float(item['price']), subtotal))

            if sale_entries:
                total = max(0, subtotal_sum - discount)
                c.execute(
                    "INSERT INTO sales (customer_name, date, total, discount, notes) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (customer, date, total, discount, notes))
                sale_id = c.fetchone()['id']

                c.executemany(
                    "INSERT INTO sale_items (sale_id, item_name, quantity, price, subtotal) VALUES (%s,%s,%s,%s,%s)",
                    [(sale_id, e[0], e[1], e[2], e[3]) for e in sale_entries])

                conn.commit()
                conn.close()

                return jsonify({
                    'success': True,
                    'sale_id': sale_id,
                    'customer_name': customer,
                    'date': date,
                    'notes': notes,
                    'discount': discount,
                    'subtotal': subtotal_sum,
                    'items': [{'name': e[0], 'quantity': e[1],
                               'price': e[2], 'subtotal': e[3]} for e in sale_entries],
                    'total': total
                })
            else:
                conn.close()
                return jsonify({'success': False, 'error': 'Please add at least one item.'}), 400

        except Exception as e:
            conn.close()
            return jsonify({'success': False, 'error': str(e)}), 500

    conn.close()
    return render_template('add_sale.html',
                           items=get_active_items(),
                           today=datetime.now().strftime('%Y-%m-%d'))


@app.route('/sales')
def view_sales():
    conn = get_db()
    c = conn.cursor()
    search = request.args.get('search', '')
    c.execute("""SELECT id, customer_name, date, total, notes
                 FROM sales WHERE customer_name LIKE %s
                 ORDER BY date DESC, id DESC""", (f'%{search}%',))
    sales = c.fetchall()

    expanded_sales = []
    for sale in sales:
        c.execute("SELECT item_name as name, quantity, price, subtotal FROM sale_items WHERE sale_id=%s", (sale['id'],))
        items = c.fetchall()
        expanded_sales.append({
            'id': sale['id'],
            'customer': sale['customer_name'],
            'date': sale['date'],
            'total': sale['total'],
            'notes': sale['notes'],
            'items': [dict(i) for i in items]
        })

    conn.close()
    return render_template('view_sales.html', sales=expanded_sales, search=search)


@app.route('/sales/delete/<int:sale_id>', methods=['POST'])
def delete_sale(sale_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM sale_items WHERE sale_id=%s", (sale_id,))
    c.execute("DELETE FROM sales WHERE id=%s", (sale_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('view_sales'))


@app.route('/sales/edit/<int:sale_id>', methods=['GET', 'POST'])
def edit_sale(sale_id):
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
    items_json = json.dumps([{**i, 'price': float(i['price'])} for i in items])

    if request.method == 'POST':
        try:
            customer   = request.form['customer_name'].strip()
            date       = request.form['date']
            notes      = request.form.get('notes', '').strip()
            discount   = float(request.form.get('discount', 0) or 0)
            item_ids   = request.form.getlist('item_id')
            quantities = request.form.getlist('quantity')

            subtotal_sum  = 0
            updated_items = []

            for item_id, qty in zip(item_ids, quantities):
                qty = int(qty)
                if qty > 0:
                    c.execute("SELECT name, price FROM items WHERE id=%s", (item_id,))
                    item = c.fetchone()
                    if item:
                        subtotal = float(item['price']) * qty
                        subtotal_sum += subtotal
                        updated_items.append((item['name'], qty, float(item['price']), subtotal))

            if updated_items:
                total = max(0, subtotal_sum - discount)
                c.execute("UPDATE sales SET customer_name=%s, date=%s, total=%s, discount=%s, notes=%s WHERE id=%s",
                          (customer, date, total, discount, notes, sale_id))
                c.execute("DELETE FROM sale_items WHERE sale_id=%s", (sale_id,))
                c.executemany(
                    "INSERT INTO sale_items (sale_id, item_name, quantity, price, subtotal) VALUES (%s,%s,%s,%s,%s)",
                    [(sale_id, i[0], i[1], i[2], i[3]) for i in updated_items])
                conn.commit()
                conn.close()
                return redirect(url_for('view_sales'))
            else:
                conn.close()
                return render_template('edit_sale.html', sale=sale, sale_items=sale_items,
                                       items=items, items_json=items_json,
                                       error="Please add at least one item.")
        except Exception as e:
            conn.close()
            return render_template('edit_sale.html', sale=sale, sale_items=sale_items,
                                   items=items, items_json=items_json, error=f"Error: {str(e)}")

    conn.close()
    return render_template('edit_sale.html', sale=sale, sale_items=sale_items,
                           items=items, items_json=items_json)


@app.route('/sales/delete-item/<item_name>', methods=['POST'])
def delete_item_sales(item_name):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT sale_id FROM sale_items WHERE item_name=%s", (item_name,))
    sale_ids = [row['sale_id'] for row in c.fetchall()]
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


# ─────────────────────────────────────────────
# ITEMS ROUTES
# ─────────────────────────────────────────────
@app.route('/items')
def manage_items():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM items ORDER BY name")
    items = [dict(i) for i in c.fetchall()]
    conn.close()
    return render_template('manage_items.html', items=items)


@app.route('/items/add', methods=['POST'])
def add_item():
    try:
        name  = request.form['name'].strip()
        price = float(request.form['price'])
        conn  = get_db()
        c     = conn.cursor()
        c.execute("INSERT INTO items (name, price, active) VALUES (%s, %s, TRUE)", (name, price))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error adding item: {e}")
    return redirect(url_for('manage_items'))


@app.route('/items/edit/<int:item_id>', methods=['POST'])
def edit_item(item_id):
    try:
        name  = request.form['name'].strip()
        price = float(request.form['price'])
        conn  = get_db()
        c     = conn.cursor()
        c.execute("UPDATE items SET name=%s, price=%s WHERE id=%s", (name, price, item_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error editing item: {e}")
    return redirect(url_for('manage_items'))


@app.route('/items/toggle/<int:item_id>', methods=['POST'])
def toggle_item(item_id):
    try:
        conn = get_db()
        c    = conn.cursor()
        c.execute("UPDATE items SET active = NOT active WHERE id=%s", (item_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error toggling item: {e}")
    return redirect(url_for('manage_items'))


@app.route('/items/delete/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    try:
        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT COUNT(*) FROM sale_items WHERE item_name=(SELECT name FROM items WHERE id=%s)", (item_id,))
        count = c.fetchone()['count']
        if count > 0:
            c.execute("UPDATE items SET active=FALSE WHERE id=%s", (item_id,))
        else:
            c.execute("DELETE FROM items WHERE id=%s", (item_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error deleting item: {e}")
    return redirect(url_for('manage_items'))


# ─────────────────────────────────────────────
# EXPENSE ROUTES
# ─────────────────────────────────────────────
@app.route('/expenses')
def view_expenses():
    conn = get_db()
    c    = conn.cursor()
    search = request.args.get('search', '')
    c.execute("""SELECT id, description, amount, category, date, notes
                 FROM expenses WHERE description LIKE %s OR category LIKE %s
                 ORDER BY date DESC, id DESC""", (f'%{search}%', f'%{search}%'))
    expenses = c.fetchall()
    c.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses")
    total_expenses = c.fetchone()['coalesce']
    conn.close()
    return render_template('view_expenses.html',
                           expenses=[dict(e) for e in expenses],
                           search=search, total_expenses=total_expenses)


@app.route('/expenses/add', methods=['GET', 'POST'])
def add_expense():
    if request.method == 'POST':
        try:
            description = request.form['description'].strip()
            amount      = float(request.form['amount'])
            category    = request.form['category'].strip()
            date        = request.form['date'] or datetime.now().strftime('%Y-%m-%d')
            notes       = request.form.get('notes', '').strip()
            conn = get_db()
            c    = conn.cursor()
            c.execute("INSERT INTO expenses (description, amount, category, date, notes) VALUES (%s,%s,%s,%s,%s)",
                      (description, amount, category, date, notes))
            conn.commit()
            conn.close()
            return redirect(url_for('view_expenses'))
        except Exception as e:
            return render_template('add_expense.html', error=f"Error: {str(e)}",
                                   today=datetime.now().strftime('%Y-%m-%d'))
    return render_template('add_expense.html', today=datetime.now().strftime('%Y-%m-%d'))


@app.route('/expenses/edit/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT * FROM expenses WHERE id=%s", (expense_id,))
    expense = c.fetchone()
    if not expense:
        conn.close()
        return "Expense not found", 404

    if request.method == 'POST':
        try:
            description = request.form['description'].strip()
            amount      = float(request.form['amount'])
            category    = request.form['category'].strip()
            date        = request.form['date']
            notes       = request.form.get('notes', '').strip()
            c.execute("UPDATE expenses SET description=%s, amount=%s, category=%s, date=%s, notes=%s WHERE id=%s",
                      (description, amount, category, date, notes, expense_id))
            conn.commit()
            conn.close()
            return redirect(url_for('view_expenses'))
        except Exception as e:
            conn.close()
            return render_template('edit_expense.html', expense=expense, error=f"Error: {str(e)}")

    conn.close()
    return render_template('edit_expense.html', expense=expense)


@app.route('/expenses/delete/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    conn = get_db()
    c    = conn.cursor()
    c.execute("DELETE FROM expenses WHERE id=%s", (expense_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('view_expenses'))


@app.route('/expenses/delete-category/<category>', methods=['POST'])
def delete_category_expenses(category):
    conn = get_db()
    c    = conn.cursor()
    c.execute("DELETE FROM expenses WHERE category=%s", (category,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)
