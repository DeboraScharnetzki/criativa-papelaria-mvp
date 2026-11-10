from pathlib import Path
import os
import sqlite3
from datetime import date
from flask import Flask, flash, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("DATABASE_PATH", str(BASE_DIR / "criativa.db"))
STATUSES = ("Pendente", "Em produção", "Concluído", "Entregue")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-chave-troque-em-producao")
app.config["DATABASE"] = DB_PATH


def get_db():
    connection = sqlite3.connect(app.config["DATABASE"])
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            order_date TEXT NOT NULL,
            deadline TEXT NOT NULL,
            value_cents INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Pendente'
                CHECK (status IN ('Pendente', 'Em produção', 'Concluído', 'Entregue')),
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE RESTRICT
        );
        """)
        db.commit()


@app.template_filter("brl")
def brl(value):
    value = (value or 0) / 100
    return ("R$ {:,.2f}".format(value)).replace(",", "X").replace(".", ",").replace("X", ".")


@app.get("/")
def index():
    with get_db() as db:
        counts = {
            "total": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "pending": db.execute("SELECT COUNT(*) FROM orders WHERE status = ?", ("Pendente",)).fetchone()[0],
            "production": db.execute("SELECT COUNT(*) FROM orders WHERE status = ?", ("Em produção",)).fetchone()[0],
            "completed": db.execute("SELECT COUNT(*) FROM orders WHERE status = ?", ("Concluído",)).fetchone()[0],
        }
        recent_orders = db.execute("""
            SELECT o.*, c.name AS client_name
            FROM orders o JOIN clients c ON c.id = o.client_id
            ORDER BY o.id DESC LIMIT 5
        """).fetchall()
    return render_template("index.html", counts=counts, recent_orders=recent_orders)


@app.route("/clientes", methods=["GET", "POST"])
def clients():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        notes = request.form.get("notes", "").strip()
        if not name or not phone:
            flash("Informe o nome e o telefone do cliente.", "error")
            return redirect(url_for("clients"))
        with get_db() as db:
            db.execute(
                "INSERT INTO clients (name, phone, email, notes) VALUES (?, ?, ?, ?)",
                (name, phone, email or None, notes or None),
            )
            db.commit()
        flash("Cliente cadastrado com sucesso.", "success")
        return redirect(url_for("clients"))

    with get_db() as db:
        client_list = db.execute("SELECT * FROM clients ORDER BY name COLLATE NOCASE").fetchall()
    return render_template("clients.html", clients=client_list)


@app.route("/pedidos/novo", methods=["GET", "POST"])
def new_order():
    with get_db() as db:
        client_list = db.execute("SELECT id, name FROM clients ORDER BY name COLLATE NOCASE").fetchall()

    if request.method == "POST":
        client_id = request.form.get("client_id", type=int)
        description = request.form.get("description", "").strip()
        order_date = request.form.get("order_date", "").strip()
        deadline = request.form.get("deadline", "").strip()
        value_text = request.form.get("value", "0").strip().replace(",", ".")
        status = request.form.get("status", "Pendente").strip()
        notes = request.form.get("notes", "").strip()

        try:
            value_cents = round(float(value_text) * 100)
            if value_cents < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Informe um valor válido e não negativo.", "error")
            return render_template("new_order.html", clients=client_list, statuses=STATUSES, today=date.today().isoformat()), 400

        if not client_id or not description or not order_date or not deadline:
            flash("Preencha cliente, descrição, data do pedido e prazo.", "error")
            return render_template("new_order.html", clients=client_list, statuses=STATUSES, today=date.today().isoformat()), 400
        if status not in STATUSES:
            flash("Selecione um status válido.", "error")
            return render_template("new_order.html", clients=client_list, statuses=STATUSES, today=date.today().isoformat()), 400
        try:
            date.fromisoformat(order_date)
            date.fromisoformat(deadline)
        except ValueError:
            flash("Informe datas válidas.", "error")
            return render_template("new_order.html", clients=client_list, statuses=STATUSES, today=date.today().isoformat()), 400
        if deadline < order_date:
            flash("O prazo não pode ser anterior à data do pedido.", "error")
            return render_template("new_order.html", clients=client_list, statuses=STATUSES, today=date.today().isoformat()), 400

        with get_db() as db:
            exists = db.execute("SELECT id FROM clients WHERE id = ?", (client_id,)).fetchone()
            if not exists:
                flash("O cliente selecionado não existe.", "error")
                return render_template("new_order.html", clients=client_list, statuses=STATUSES, today=date.today().isoformat()), 400
            db.execute("""
                INSERT INTO orders
                (client_id, description, order_date, deadline, value_cents, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (client_id, description, order_date, deadline, value_cents, status, notes or None))
            db.commit()
        flash("Pedido cadastrado com sucesso.", "success")
        return redirect(url_for("orders"))

    return render_template("new_order.html", clients=client_list, statuses=STATUSES, today=date.today().isoformat())


@app.get("/pedidos")
def orders():
    search = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "").strip()
    query = """
        SELECT o.*, c.name AS client_name
        FROM orders o JOIN clients c ON c.id = o.client_id
        WHERE (c.name LIKE ? OR o.description LIKE ?)
    """
    params = [f"%{search}%", f"%{search}%"]
    if status_filter in STATUSES:
        query += " AND o.status = ?"
        params.append(status_filter)
    query += " ORDER BY o.deadline ASC, o.id DESC"
    with get_db() as db:
        order_list = db.execute(query, params).fetchall()
    return render_template("orders.html", orders=order_list, statuses=STATUSES, q=search, status_filter=status_filter)


@app.post("/pedidos/<int:order_id>/status")
def update_status(order_id):
    status = request.form.get("status", "").strip()
    if status not in STATUSES:
        flash("Status inválido.", "error")
        return redirect(url_for("orders"))
    with get_db() as db:
        cursor = db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        db.commit()
    if cursor.rowcount:
        flash("Status do pedido atualizado.", "success")
    else:
        flash("Pedido não encontrado.", "error")
    return redirect(url_for("orders"))


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


init_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
