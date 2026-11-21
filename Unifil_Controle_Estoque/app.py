from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = BASE_DIR / "instance" / "estoque.db"


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-this-key"),
        DATABASE=str(DEFAULT_DATABASE),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    @app.before_request
    def ensure_database() -> None:
        if not app.config.get("DATABASE_INITIALIZED"):
            with app.app_context():
                db = get_db()
                db.executescript((BASE_DIR / "schema.sql").read_text(encoding="utf-8"))
                db.commit()
                app.config["DATABASE_INITIALIZED"] = True

    @app.teardown_appcontext
    def close_db(exception: BaseException | None = None) -> None:
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.get("/")
    def dashboard():
        db = get_db()
        stats = {
            "products": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "suppliers": db.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0],
            "movements": db.execute("SELECT COUNT(*) FROM stock_movements").fetchone()[0],
        }
        stock_rows = db.execute(product_stock_query() + " GROUP BY p.id ORDER BY p.name COLLATE NOCASE").fetchall()
        stats["low_stock"] = sum(1 for item in stock_rows if item["stock"] <= item["min_stock"])
        recent = db.execute(movements_query() + " ORDER BY m.created_at DESC, m.id DESC LIMIT 8").fetchall()
        return render_template("dashboard.html", stats=stats, recent=recent)

    @app.get("/products")
    def products_list():
        search = request.args.get("q", "").strip()
        sql = product_stock_query()
        params: list[Any] = []
        if search:
            sql += " WHERE p.name LIKE ? OR p.sku LIKE ? OR p.category LIKE ?"
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern])
        sql += " GROUP BY p.id ORDER BY p.name COLLATE NOCASE"
        rows = get_db().execute(sql, params).fetchall()
        return render_template("products/list.html", products=rows, search=search)

    @app.route("/products/new", methods=["GET", "POST"])
    def product_new():
        db = get_db()
        suppliers = db.execute("SELECT id, name FROM suppliers ORDER BY name COLLATE NOCASE").fetchall()
        values = product_form_values(request.form) if request.method == "POST" else None
        if request.method == "POST":
            error = validate_product(values)
            if error:
                flash(error, "error")
            else:
                try:
                    db.execute(
                        """INSERT INTO products (sku, name, description, category, unit, min_stock, supplier_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (values["sku"], values["name"], values["description"], values["category"],
                         values["unit"], values["min_stock"], values["supplier_id"]),
                    )
                    db.commit()
                    flash("Produto cadastrado com sucesso.", "success")
                    return redirect(url_for("products_list"))
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("Já existe um produto com esse SKU ou o fornecedor informado é inválido.", "error")
        return render_template("products/form.html", product=values, suppliers=suppliers, page_title="Novo produto")

    @app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
    def product_edit(product_id: int):
        db = get_db()
        existing = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if existing is None:
            abort(404)
        suppliers = db.execute("SELECT id, name FROM suppliers ORDER BY name COLLATE NOCASE").fetchall()
        values = product_form_values(request.form) if request.method == "POST" else dict(existing)
        if request.method == "POST":
            error = validate_product(values)
            if error:
                flash(error, "error")
            else:
                try:
                    db.execute(
                        """UPDATE products SET sku=?, name=?, description=?, category=?, unit=?, min_stock=?,
                           supplier_id=?, updated_at=datetime('now', 'localtime') WHERE id=?""",
                        (values["sku"], values["name"], values["description"], values["category"],
                         values["unit"], values["min_stock"], values["supplier_id"], product_id),
                    )
                    db.commit()
                    flash("Produto atualizado com sucesso.", "success")
                    return redirect(url_for("products_list"))
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("Já existe um produto com esse SKU ou o fornecedor informado é inválido.", "error")
        return render_template("products/form.html", product=values, suppliers=suppliers, page_title="Editar produto")

    @app.post("/products/<int:product_id>/delete")
    def product_delete(product_id: int):
        db = get_db()
        try:
            cursor = db.execute("DELETE FROM products WHERE id = ?", (product_id,))
            if cursor.rowcount == 0:
                abort(404)
            db.commit()
            flash("Produto excluído com sucesso.", "success")
        except sqlite3.IntegrityError:
            db.rollback()
            flash("Este produto possui movimentações e não pode ser excluído. Preserve o histórico de estoque.", "error")
        return redirect(url_for("products_list"))

    @app.get("/suppliers")
    def suppliers_list():
        rows = get_db().execute(
            """SELECT s.*, COUNT(p.id) AS product_count FROM suppliers s
               LEFT JOIN products p ON p.supplier_id = s.id
               GROUP BY s.id ORDER BY s.name COLLATE NOCASE"""
        ).fetchall()
        return render_template("suppliers/list.html", suppliers=rows)

    @app.route("/suppliers/new", methods=["GET", "POST"])
    def supplier_new():
        values = supplier_form_values(request.form) if request.method == "POST" else None
        if request.method == "POST":
            error = validate_supplier(values)
            if error:
                flash(error, "error")
            else:
                db = get_db()
                db.execute("INSERT INTO suppliers (name, document, phone, email) VALUES (?, ?, ?, ?)",
                           (values["name"], values["document"], values["phone"], values["email"]))
                db.commit()
                flash("Fornecedor cadastrado com sucesso.", "success")
                return redirect(url_for("suppliers_list"))
        return render_template("suppliers/form.html", supplier=values, page_title="Novo fornecedor")

    @app.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
    def supplier_edit(supplier_id: int):
        db = get_db()
        existing = db.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        if existing is None:
            abort(404)
        values = supplier_form_values(request.form) if request.method == "POST" else dict(existing)
        if request.method == "POST":
            error = validate_supplier(values)
            if error:
                flash(error, "error")
            else:
                db.execute("UPDATE suppliers SET name=?, document=?, phone=?, email=? WHERE id=?",
                           (values["name"], values["document"], values["phone"], values["email"], supplier_id))
                db.commit()
                flash("Fornecedor atualizado com sucesso.", "success")
                return redirect(url_for("suppliers_list"))
        return render_template("suppliers/form.html", supplier=values, page_title="Editar fornecedor")

    @app.post("/suppliers/<int:supplier_id>/delete")
    def supplier_delete(supplier_id: int):
        db = get_db()
        try:
            cursor = db.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
            if cursor.rowcount == 0:
                abort(404)
            db.commit()
            flash("Fornecedor excluído com sucesso.", "success")
        except sqlite3.IntegrityError:
            db.rollback()
            flash("Este fornecedor está associado a produtos e não pode ser excluído.", "error")
        return redirect(url_for("suppliers_list"))

    @app.route("/movements/new", methods=["GET", "POST"])
    def movement_new():
        db = get_db()
        products = db.execute(product_stock_query() + " GROUP BY p.id ORDER BY p.name COLLATE NOCASE").fetchall()
        values = request.form.to_dict() if request.method == "POST" else None
        if request.method == "POST":
            error, movement = validate_movement(values)
            if error:
                flash(error, "error")
            else:
                try:
                    db.execute("BEGIN IMMEDIATE")
                    current = get_stock(db, movement["product_id"])
                    if movement["movement_type"] == "SAIDA" and movement["quantity"] > current:
                        db.rollback()
                        flash(f"Estoque insuficiente. Saldo atual: {format_quantity(current)}.", "error")
                    else:
                        db.execute(
                            "INSERT INTO stock_movements (product_id, movement_type, quantity, note) VALUES (?, ?, ?, ?)",
                            (movement["product_id"], movement["movement_type"], movement["quantity"], movement["note"]),
                        )
                        db.commit()
                        flash("Movimentação registrada com sucesso.", "success")
                        return redirect(url_for("movements_list"))
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("Não foi possível registrar a movimentação. Verifique os dados informados.", "error")
        return render_template("movements/form.html", products=products, values=values)

    @app.get("/movements")
    def movements_list():
        db = get_db()
        product_id = request.args.get("product_id", type=int)
        movement_type = request.args.get("type", "").upper()
        sql = movements_query()
        clauses: list[str] = []
        params: list[Any] = []
        if product_id:
            clauses.append("m.product_id = ?")
            params.append(product_id)
        if movement_type in {"ENTRADA", "SAIDA"}:
            clauses.append("m.movement_type = ?")
            params.append(movement_type)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY m.created_at DESC, m.id DESC LIMIT 200"
        rows = db.execute(sql, params).fetchall()
        products = db.execute("SELECT id, sku, name FROM products ORDER BY name COLLATE NOCASE").fetchall()
        return render_template("movements/list.html", movements=rows, products=products,
                               selected_product=product_id, selected_type=movement_type)

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("404.html"), 404

    # Formata quantidades sem casas decimais desnecessárias (ex.: 10, e não 10.0).
    app.jinja_env.filters["qty"] = lambda value: f"{float(value):g}"
    return app


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db = sqlite3.connect(current_database())
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        g.db = db
    return g.db


def current_database() -> str:
    from flask import current_app
    return current_app.config["DATABASE"]


def product_stock_query() -> str:
    return """SELECT p.*, s.name AS supplier_name,
              COALESCE(SUM(CASE WHEN m.movement_type='ENTRADA' THEN m.quantity
                                WHEN m.movement_type='SAIDA' THEN -m.quantity ELSE 0 END), 0) AS stock
              FROM products p
              LEFT JOIN suppliers s ON s.id = p.supplier_id
              LEFT JOIN stock_movements m ON m.product_id = p.id"""


def movements_query() -> str:
    return """SELECT m.*, p.sku, p.name AS product_name, p.unit
              FROM stock_movements m JOIN products p ON p.id=m.product_id"""


def product_form_values(form) -> dict[str, Any]:
    supplier_raw = str(form.get("supplier_id", "")).strip()
    min_stock_raw = str(form.get("min_stock", "0")).strip().replace(",", ".")
    try:
        min_stock = float(min_stock_raw or 0)
    except ValueError:
        min_stock = -1
    try:
        supplier_id = int(supplier_raw) if supplier_raw else None
    except ValueError:
        supplier_id = -1
    return {
        "sku": str(form.get("sku", "")).strip(),
        "name": str(form.get("name", "")).strip(),
        "description": str(form.get("description", "")).strip(),
        "category": str(form.get("category", "")).strip(),
        "unit": str(form.get("unit", "un")).strip() or "un",
        "min_stock": min_stock,
        "supplier_id": supplier_id,
    }


def validate_product(values: dict[str, Any]) -> str | None:
    if not values["sku"] or not values["name"]:
        return "Preencha o SKU e o nome do produto."
    if len(values["sku"]) > 40 or len(values["name"]) > 120:
        return "SKU deve ter até 40 caracteres e nome até 120 caracteres."
    if values["min_stock"] < 0:
        return "Estoque mínimo deve ser um número igual ou maior que zero."
    if values["supplier_id"] == -1:
        return "Fornecedor inválido."
    return None


def supplier_form_values(form) -> dict[str, str]:
    return {
        "name": str(form.get("name", "")).strip(),
        "document": str(form.get("document", "")).strip(),
        "phone": str(form.get("phone", "")).strip(),
        "email": str(form.get("email", "")).strip(),
    }


def validate_supplier(values: dict[str, str]) -> str | None:
    if not values["name"]:
        return "O nome do fornecedor é obrigatório."
    if len(values["name"]) > 120:
        return "O nome do fornecedor deve ter até 120 caracteres."
    if values["email"] and ("@" not in values["email"] or len(values["email"]) > 160):
        return "Informe um e-mail válido."
    return None


def validate_movement(form: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    try:
        product_id = int(form.get("product_id", ""))
    except (TypeError, ValueError):
        return "Selecione um produto válido.", {}
    movement_type = str(form.get("movement_type", "")).upper()
    try:
        quantity = float(str(form.get("quantity", "")).replace(",", "."))
    except (TypeError, ValueError):
        return "Informe uma quantidade numérica maior que zero.", {}
    if movement_type not in {"ENTRADA", "SAIDA"}:
        return "Tipo de movimentação inválido.", {}
    if quantity <= 0:
        return "A quantidade deve ser maior que zero.", {}
    note = str(form.get("note", "")).strip()
    if len(note) > 240:
        return "A observação deve ter até 240 caracteres.", {}
    product = get_db().execute("SELECT id FROM products WHERE id=?", (product_id,)).fetchone()
    if product is None:
        return "O produto selecionado não existe.", {}
    return None, {"product_id": product_id, "movement_type": movement_type, "quantity": quantity, "note": note}


def get_stock(db: sqlite3.Connection, product_id: int) -> float:
    row = db.execute(
        """SELECT COALESCE(SUM(CASE WHEN movement_type='ENTRADA' THEN quantity
                                     WHEN movement_type='SAIDA' THEN -quantity ELSE 0 END),0)
           FROM stock_movements WHERE product_id=?""", (product_id,)
    ).fetchone()
    return float(row[0])


def format_quantity(value: float) -> str:
    return f"{value:g}"


from flask import current_app  # noqa: E402  (import kept near helper dependencies)

app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
