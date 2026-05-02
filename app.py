from flask import Flask, render_template, request, redirect, url_for, jsonify, make_response
import psycopg2
import psycopg2.extras
from datetime import datetime
import json
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# ─────────────────────────────────────────────────────────────────
# DATABASE
# On Vercel serverless, connection pools don't survive between
# invocations. We use a module-level cached connection instead,
# with autocommit=False and a keep-alive ping before each use.
# This avoids the ~1-2s SSL handshake on every request.
# ─────────────────────────────────────────────────────────────────
_conn = None

def _build_uri():
    uri = os.environ.get('DATABASE_URL', '')
    if uri.startswith('postgres://'):
        uri = uri.replace('postgres://', 'postgresql://', 1)
    if not uri:
        raise RuntimeError('DATABASE_URL not set')
    return uri

def get_db():
    """Return a live connection, reconnecting if needed."""
    global _conn
    try:
        if _conn is None or _conn.closed:
            raise Exception('no connection')
        # Fast ping — if the connection died, this raises
        _conn.cursor().execute('SELECT 1')
    except Exception:
        _conn = psycopg2.connect(
            _build_uri(),
            sslmode='require',
            cursor_factory=psycopg2.extras.RealDictCursor,
            connect_timeout=5,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=5,
            keepalives_count=3,
        )
    return _conn


# ─────────────────────────────────────────────────────────────────
# JINJA FILTERS
# ─────────────────────────────────────────────────────────────────
@app.template_filter('money')
def money_filter(value):
    """Format a number as ₱1,234.56"""
    try:
        return '₱{:,.2f}'.format(float(value))
    except (TypeError, ValueError):
        return '₱0.00'

@app.template_filter('short_date')
def short_date_filter(value):
    """Strip the time portion from a datetime/string: 2026-05-02"""
    if value is None:
        return ''
    s = str(value)
    return s[:10]  # YYYY-MM-DD


# ─────────────────────────────────────────────────────────────────
# INIT DB
# ─────────────────────────────────────────────────────────────────
def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    price DECIMAL(10,2) NOT NULL,
                    active BOOLEAN DEFAULT TRUE,
                    sort_order INTEGER DEFAULT 0
                )''')

    c.execute('''CREATE TABLE IF NOT EXISTS sales (
                    id SERIAL PRIMARY KEY,
                    customer_name VARCHAR(255) NOT NULL,
                    date DATE NOT NULL,
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
                    date DATE NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')

    # ── Migrations (all safe to re-run) ──────────────────────────
    c.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='sales' AND column_name='discount')
            THEN ALTER TABLE sales ADD COLUMN discount DECIMAL(10,2) DEFAULT 0; END IF;
        END $$;
    """)
    c.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='items' AND column_name='sort_order')
            THEN ALTER TABLE items ADD COLUMN sort_order INTEGER DEFAULT 0; END IF;
        END $$;
    """)
    c.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                           WHERE table_name='items' AND column_name='id'
                           AND column_default LIKE 'nextval%')
            THEN
                CREATE SEQUENCE IF NOT EXISTS items_id_seq;
                ALTER TABLE items ALTER COLUMN id SET DEFAULT nextval('items_id_seq');
                PERFORM setval('items_id_seq', COALESCE((SELECT MAX(id) FROM items), 0) + 1);
            END IF;
        END $$;
    """)

    # Seed sort_order for items that have 0 (first-time migration)
    c.execute("UPDATE items SET sort_order = id WHERE sort_order = 0")

    # Seed default items if empty
    c.execute("SELECT COUNT(*) as cnt FROM items")
    if c.fetchone()['cnt'] == 0:
        for i, (name, price) in enumerate([
            ("White Springtail", 120.00),
            ("Orange Springtail", 250.00),
            ("Agnara", 120.00),
            ("Porcellio Sevilla", 250.00),
        ], 1):
            c.execute("INSERT INTO items (name,price,active,sort_order) VALUES (%s,%s,TRUE,%s)",
                      (name, price, i))

    conn.commit()


try:
    init_db()
    print("DB initialized.")
except Exception as e:
    print(f"WARNING: init_db skipped: {e}")


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────
def get_active_items():
    c = get_db().cursor()
    c.execute("SELECT * FROM items WHERE active=TRUE ORDER BY sort_order ASC, id ASC")
    return [dict(r) for r in c.fetchall()]


def get_sale_data(sale_id):
    c = get_db().cursor()
    c.execute("SELECT * FROM sales WHERE id=%s", (sale_id,))
    sale = c.fetchone()
    if not sale:
        return None
    c.execute("SELECT * FROM sale_items WHERE sale_id=%s", (sale_id,))
    items = [dict(r) for r in c.fetchall()]
    discount     = float(sale.get('discount') or 0)
    subtotal_sum = sum(float(i['subtotal']) for i in items)
    return {
        'sale_id':       sale['id'],
        'customer_name': sale['customer_name'],
        'date':          str(sale['date'])[:10],
        'notes':         sale['notes'] or '',
        'discount':      discount,
        'subtotal':      subtotal_sum,
        'total':         float(sale['total']),
        'items': [{'name': i['item_name'], 'quantity': i['quantity'],
                   'price': float(i['price']), 'subtotal': float(i['subtotal'])}
                  for i in items],
    }


# ─────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────
@app.route('/')
def dashboard():
    c = get_db().cursor()

    c.execute("SELECT COALESCE(SUM(total),0) as v FROM sales");             total_revenue     = c.fetchone()['v']
    c.execute("SELECT COUNT(*) as v FROM sales");                           total_transactions= c.fetchone()['v']
    c.execute("SELECT COALESCE(SUM(amount),0) as v FROM expenses");         total_expenses    = c.fetchone()['v']
    net_profit = total_revenue - total_expenses

    c.execute("SELECT id,customer_name,date,total FROM sales ORDER BY date DESC,id DESC LIMIT 5")
    recent_sales = c.fetchall()

    c.execute("SELECT id,description,amount,category,date FROM expenses ORDER BY date DESC,id DESC LIMIT 5")
    recent_expenses = c.fetchall()

    c.execute("""SELECT si.item_name, i.id as item_id,
                        SUM(si.quantity) as total_qty, SUM(si.subtotal) as total_sales
                 FROM sale_items si LEFT JOIN items i ON si.item_name=i.name
                 GROUP BY si.item_name,i.id ORDER BY total_qty DESC LIMIT 5""")
    top_items = c.fetchall()

    c.execute("""SELECT category, SUM(amount) as total,
                        STRING_AGG(id::text,',') as expense_ids
                 FROM expenses GROUP BY category ORDER BY total DESC LIMIT 5""")
    expense_breakdown = c.fetchall()

    return render_template('dashboard.html',
                           revenue=total_revenue, transactions=total_transactions,
                           expenses=total_expenses, net_profit=net_profit,
                           recent_sales=recent_sales, recent_expenses=recent_expenses,
                           top_items=top_items, expense_breakdown=expense_breakdown)


# ─────────────────────────────────────────────────────────────────
# ANALYTICS APIs
# ─────────────────────────────────────────────────────────────────
@app.route('/api/charts/monthly-sales')
def api_monthly_sales():
    c = get_db().cursor()
    c.execute("""SELECT to_char(date,'YYYY-MM') as month, SUM(total) as revenue, COUNT(*) as transactions
                 FROM sales GROUP BY to_char(date,'YYYY-MM') ORDER BY month DESC LIMIT 12""")
    data = [dict(r) for r in c.fetchall()]
    data.reverse()
    return jsonify(data)


@app.route('/api/charts/item-sales')
def api_item_sales():
    c = get_db().cursor()
    c.execute("SELECT item_name,SUM(quantity) as total_qty,SUM(subtotal) as total_sales FROM sale_items GROUP BY item_name ORDER BY total_sales DESC")
    return jsonify([dict(r) for r in c.fetchall()])


@app.route('/api/charts/expense-breakdown')
def api_expense_breakdown():
    c = get_db().cursor()
    c.execute("SELECT category,SUM(amount) as total FROM expenses GROUP BY category ORDER BY total DESC")
    return jsonify([dict(r) for r in c.fetchall()])


@app.route('/api/charts/monthly-comparison')
def api_monthly_comparison():
    c = get_db().cursor()
    c.execute("SELECT to_char(date,'YYYY-MM') as month,SUM(total) as amount FROM sales GROUP BY to_char(date,'YYYY-MM')")
    sd = [dict(r) for r in c.fetchall()]
    c.execute("SELECT to_char(date,'YYYY-MM') as month,SUM(amount) as amount FROM expenses GROUP BY to_char(date,'YYYY-MM')")
    ed = [dict(r) for r in c.fetchall()]
    months = sorted(set(r['month'] for r in sd+ed))
    result = [{'month':m,
               'revenue':  next((r['amount'] for r in sd if r['month']==m),0),
               'expenses': next((r['amount'] for r in ed if r['month']==m),0),
               'profit':   next((r['amount'] for r in sd if r['month']==m),0)
                           -next((r['amount'] for r in ed if r['month']==m),0)}
              for m in months]
    return jsonify(result[-12:])


@app.route('/api/analytics/daily')
def api_analytics_daily():
    c = get_db().cursor()
    c.execute("""SELECT to_char(date,'YYYY-MM-DD') as day,SUM(total) as revenue,COUNT(*) as transactions
                 FROM sales WHERE date>=NOW()-INTERVAL '30 days'
                 GROUP BY to_char(date,'YYYY-MM-DD') ORDER BY day""")
    return jsonify([dict(r) for r in c.fetchall()])


@app.route('/api/analytics/weekly')
def api_analytics_weekly():
    c = get_db().cursor()
    c.execute("""SELECT to_char(date_trunc('week',date),'YYYY-MM-DD') as week_start,
                        SUM(total) as revenue,COUNT(*) as transactions
                 FROM sales WHERE date>=NOW()-INTERVAL '12 weeks'
                 GROUP BY date_trunc('week',date) ORDER BY week_start""")
    return jsonify([dict(r) for r in c.fetchall()])


@app.route('/api/analytics/monthly')
def api_analytics_monthly():
    c = get_db().cursor()
    c.execute("""SELECT to_char(date,'YYYY-MM') as month,SUM(total) as revenue,COUNT(*) as transactions
                 FROM sales WHERE date>=NOW()-INTERVAL '12 months'
                 GROUP BY to_char(date,'YYYY-MM') ORDER BY month""")
    return jsonify([dict(r) for r in c.fetchall()])


@app.route('/api/analytics/yearly')
def api_analytics_yearly():
    c = get_db().cursor()
    c.execute("SELECT to_char(date,'YYYY') as year,SUM(total) as revenue,COUNT(*) as transactions FROM sales GROUP BY to_char(date,'YYYY') ORDER BY year")
    return jsonify([dict(r) for r in c.fetchall()])


# ─────────────────────────────────────────────────────────────────
# ITEMS — REORDER
# ─────────────────────────────────────────────────────────────────
@app.route('/items/reorder', methods=['POST'])
def reorder_items():
    try:
        ids = request.get_json().get('ids', [])
        if not ids:
            return jsonify({'success': False}), 400
        conn = get_db()
        c = conn.cursor()
        for idx, item_id in enumerate(ids):
            c.execute("UPDATE items SET sort_order=%s WHERE id=%s", (idx, item_id))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────
# RECEIPT
# ─────────────────────────────────────────────────────────────────
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
    lines = ["="*40, "       MICROFAUNA SALES RECEIPT", "="*40,
             f"Receipt #: {data['sale_id']}", f"Customer : {data['customer_name']}",
             f"Date     : {data['date']}"]
    if data['notes']:
        lines.append(f"Notes    : {data['notes']}")
    lines += ["-"*40, f"{'ITEM':<20} {'QTY':>4} {'PRICE':>8} {'TOTAL':>8}", "-"*40]
    for item in data['items']:
        lines.append(f"{item['name']:<20} {item['quantity']:>4} P{item['price']:>7,.2f} P{item['subtotal']:>7,.2f}")
    lines.append("-"*40)
    if data['discount'] > 0:
        lines.append(f"{'DISCOUNT':>34} P{data['discount']:>7,.2f}")
    lines += [f"{'TOTAL':>34} P{data['total']:>7,.2f}", "="*40,
              "    Thank you for your purchase!", "="*40]
    resp = make_response("\n".join(lines))
    resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
    resp.headers['Content-Disposition'] = \
        f'attachment; filename=receipt_{sale_id}_{data["customer_name"].replace(" ","_")}.txt'
    return resp


# ─────────────────────────────────────────────────────────────────
# SALES
# ─────────────────────────────────────────────────────────────────
@app.route('/add-sale', methods=['GET', 'POST'])
def add_sale():
    if request.method == 'POST':
        conn = get_db()
        c = conn.cursor()
        try:
            customer   = request.form['customer_name'].strip()
            date       = request.form['date'] or datetime.now().strftime('%Y-%m-%d')
            notes      = request.form.get('notes','').strip()
            discount   = float(request.form.get('discount',0) or 0)
            item_ids   = request.form.getlist('item_id')
            quantities = request.form.getlist('quantity')

            subtotal_sum = 0
            entries = []
            for item_id, qty in zip(item_ids, quantities):
                qty = int(qty)
                if qty > 0:
                    c.execute("SELECT name,price FROM items WHERE id=%s AND active=TRUE", (item_id,))
                    item = c.fetchone()
                    if item:
                        sub = float(item['price']) * qty
                        subtotal_sum += sub
                        entries.append((item['name'], qty, float(item['price']), sub))

            if not entries:
                return jsonify({'success':False,'error':'Please add at least one item.'}), 400

            total = max(0, subtotal_sum - discount)
            c.execute("INSERT INTO sales (customer_name,date,total,discount,notes) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                      (customer,date,total,discount,notes))
            sale_id = c.fetchone()['id']
            c.executemany("INSERT INTO sale_items (sale_id,item_name,quantity,price,subtotal) VALUES (%s,%s,%s,%s,%s)",
                          [(sale_id,e[0],e[1],e[2],e[3]) for e in entries])
            conn.commit()
            return jsonify({'success':True,'sale_id':sale_id,'customer_name':customer,
                            'date':date,'notes':notes,'discount':discount,
                            'subtotal':subtotal_sum,'total':total,
                            'items':[{'name':e[0],'quantity':e[1],'price':e[2],'subtotal':e[3]} for e in entries]})
        except Exception as e:
            conn.rollback()
            return jsonify({'success':False,'error':str(e)}), 500

    return render_template('add_sale.html', items=get_active_items(),
                           today=datetime.now().strftime('%Y-%m-%d'))


@app.route('/sales')
def view_sales():
    c = get_db().cursor()
    search = request.args.get('search','')
    c.execute("SELECT id,customer_name,date,total,notes FROM sales WHERE customer_name LIKE %s ORDER BY date DESC,id DESC",
              (f'%{search}%',))
    sales = c.fetchall()
    expanded = []
    for sale in sales:
        c.execute("SELECT item_name as name,quantity,price,subtotal FROM sale_items WHERE sale_id=%s", (sale['id'],))
        expanded.append({'id':sale['id'],'customer':sale['customer_name'],
                         'date':str(sale['date'])[:10],
                         'total':sale['total'],'notes':sale['notes'],
                         'items':[dict(i) for i in c.fetchall()]})
    return render_template('view_sales.html', sales=expanded, search=search)


@app.route('/sales/delete/<int:sale_id>', methods=['POST'])
def delete_sale(sale_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM sale_items WHERE sale_id=%s", (sale_id,))
    c.execute("DELETE FROM sales WHERE id=%s", (sale_id,))
    conn.commit()
    return redirect(url_for('view_sales'))


@app.route('/sales/edit/<int:sale_id>', methods=['GET', 'POST'])
def edit_sale(sale_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM sales WHERE id=%s", (sale_id,))
    sale = c.fetchone()
    if not sale:
        return "Sale not found", 404
    c.execute("SELECT * FROM sale_items WHERE sale_id=%s", (sale_id,))
    sale_items = [dict(r) for r in c.fetchall()]
    items = get_active_items()
    items_json = json.dumps([{**i,'price':float(i['price'])} for i in items])

    if request.method == 'POST':
        try:
            customer   = request.form['customer_name'].strip()
            date       = request.form['date']
            notes      = request.form.get('notes','').strip()
            discount   = float(request.form.get('discount',0) or 0)
            item_ids   = request.form.getlist('item_id')
            quantities = request.form.getlist('quantity')
            subtotal_sum = 0
            updated = []
            for item_id, qty in zip(item_ids, quantities):
                qty = int(qty)
                if qty > 0:
                    c.execute("SELECT name,price FROM items WHERE id=%s", (item_id,))
                    item = c.fetchone()
                    if item:
                        sub = float(item['price']) * qty
                        subtotal_sum += sub
                        updated.append((item['name'],qty,float(item['price']),sub))
            if not updated:
                return render_template('edit_sale.html', sale=sale, sale_items=sale_items,
                                       items=items, items_json=items_json,
                                       error="Please add at least one item.")
            total = max(0, subtotal_sum - discount)
            c.execute("UPDATE sales SET customer_name=%s,date=%s,total=%s,discount=%s,notes=%s WHERE id=%s",
                      (customer,date,total,discount,notes,sale_id))
            c.execute("DELETE FROM sale_items WHERE sale_id=%s", (sale_id,))
            c.executemany("INSERT INTO sale_items (sale_id,item_name,quantity,price,subtotal) VALUES (%s,%s,%s,%s,%s)",
                          [(sale_id,u[0],u[1],u[2],u[3]) for u in updated])
            conn.commit()
            return redirect(url_for('view_sales'))
        except Exception as e:
            conn.rollback()
            return render_template('edit_sale.html', sale=sale, sale_items=sale_items,
                                   items=items, items_json=items_json, error=f"Error: {str(e)}")

    return render_template('edit_sale.html', sale=sale, sale_items=sale_items,
                           items=items, items_json=items_json)


@app.route('/sales/delete-item/<item_name>', methods=['POST'])
def delete_item_sales(item_name):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT sale_id FROM sale_items WHERE item_name=%s", (item_name,))
    sale_ids = [r['sale_id'] for r in c.fetchall()]
    c.execute("DELETE FROM sale_items WHERE item_name=%s", (item_name,))
    for sid in sale_ids:
        c.execute("SELECT SUM(subtotal) as s FROM sale_items WHERE sale_id=%s", (sid,))
        new_total = c.fetchone()['s']
        if not new_total:
            c.execute("DELETE FROM sales WHERE id=%s", (sid,))
        else:
            c.execute("UPDATE sales SET total=%s WHERE id=%s", (new_total,sid))
    conn.commit()
    return redirect(url_for('dashboard'))


# ─────────────────────────────────────────────────────────────────
# ITEMS
# ─────────────────────────────────────────────────────────────────
@app.route('/items')
def manage_items():
    c = get_db().cursor()
    c.execute("SELECT * FROM items ORDER BY sort_order ASC, id ASC")
    return render_template('manage_items.html', items=[dict(i) for i in c.fetchall()])


@app.route('/items/add', methods=['POST'])
def add_item():
    conn = get_db()
    c = conn.cursor()
    try:
        name  = request.form['name'].strip()
        price = float(request.form['price'])
        # Get the next sort_order value
        c.execute("SELECT MAX(sort_order) as mx FROM items")
        row = c.fetchone()
        next_order = (row['mx'] or 0) + 1
        c.execute("INSERT INTO items (name,price,active,sort_order) VALUES (%s,%s,TRUE,%s)",
                  (name, price, next_order))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error adding item: {e}")
    return redirect(url_for('manage_items'))


@app.route('/items/edit/<int:item_id>', methods=['POST'])
def edit_item(item_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE items SET name=%s,price=%s WHERE id=%s",
                  (request.form['name'].strip(), float(request.form['price']), item_id))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error editing item: {e}")
    return redirect(url_for('manage_items'))


@app.route('/items/toggle/<int:item_id>', methods=['POST'])
def toggle_item(item_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("UPDATE items SET active = NOT active WHERE id=%s", (item_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error toggling: {e}")
    return redirect(url_for('manage_items'))


@app.route('/items/delete/<int:item_id>', methods=['POST'])
def delete_item(item_id):
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("SELECT COUNT(*) as cnt FROM sale_items WHERE item_name=(SELECT name FROM items WHERE id=%s)", (item_id,))
        if c.fetchone()['cnt'] > 0:
            c.execute("UPDATE items SET active=FALSE WHERE id=%s", (item_id,))
        else:
            c.execute("DELETE FROM items WHERE id=%s", (item_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error deleting item: {e}")
    return redirect(url_for('manage_items'))


# ─────────────────────────────────────────────────────────────────
# EXPENSES
# ─────────────────────────────────────────────────────────────────
@app.route('/expenses')
def view_expenses():
    c = get_db().cursor()
    search = request.args.get('search','')
    c.execute("SELECT id,description,amount,category,date,notes FROM expenses WHERE description LIKE %s OR category LIKE %s ORDER BY date DESC,id DESC",
              (f'%{search}%',f'%{search}%'))
    expenses = [dict(e) for e in c.fetchall()]
    c.execute("SELECT COALESCE(SUM(amount),0) as v FROM expenses")
    total_expenses = c.fetchone()['v']
    return render_template('view_expenses.html', expenses=expenses, search=search, total_expenses=total_expenses)


@app.route('/expenses/add', methods=['GET', 'POST'])
def add_expense():
    if request.method == 'POST':
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO expenses (description,amount,category,date,notes) VALUES (%s,%s,%s,%s,%s)",
                      (request.form['description'].strip(), float(request.form['amount']),
                       request.form['category'].strip(),
                       request.form['date'] or datetime.now().strftime('%Y-%m-%d'),
                       request.form.get('notes','').strip()))
            conn.commit()
            return redirect(url_for('view_expenses'))
        except Exception as e:
            conn.rollback()
            return render_template('add_expense.html', error=str(e),
                                   today=datetime.now().strftime('%Y-%m-%d'))
    return render_template('add_expense.html', today=datetime.now().strftime('%Y-%m-%d'))


@app.route('/expenses/edit/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM expenses WHERE id=%s", (expense_id,))
    expense = c.fetchone()
    if not expense:
        return "Expense not found", 404
    if request.method == 'POST':
        try:
            c.execute("UPDATE expenses SET description=%s,amount=%s,category=%s,date=%s,notes=%s WHERE id=%s",
                      (request.form['description'].strip(), float(request.form['amount']),
                       request.form['category'].strip(), request.form['date'],
                       request.form.get('notes','').strip(), expense_id))
            conn.commit()
            return redirect(url_for('view_expenses'))
        except Exception as e:
            conn.rollback()
            return render_template('edit_expense.html', expense=expense, error=str(e))
    return render_template('edit_expense.html', expense=expense)


@app.route('/expenses/delete/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM expenses WHERE id=%s", (expense_id,))
    conn.commit()
    return redirect(url_for('view_expenses'))


@app.route('/expenses/delete-category/<category>', methods=['POST'])
def delete_category_expenses(category):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM expenses WHERE category=%s", (category,))
    conn.commit()
    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True)
