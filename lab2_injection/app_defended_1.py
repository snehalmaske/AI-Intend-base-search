"""
app_defended_1.py

Hardened version of the lab2 app with additional defence-in-depth layers on
top of the AST-based calc guard:

  1. Input validation & sanitization  -> reject malformed input up front
  2. SQLAlchemy ORM for queries        -> parameterized by design, no raw SQL
  3. Least-privilege DB credentials    -> query path uses a READ-ONLY connection
                                          (SQLite has no user accounts, so least
                                          privilege is enforced via mode=ro)

Run on port 5003 so it can coexist with app_vulnerable.py (5001) and
app_defended.py (5002).
"""

import ast
import re

from flask import Flask, request, jsonify
from sqlalchemy import create_engine, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

app = Flask(__name__)

# --- Defence 3: least-privilege DB access --------------------------------
# SQLite has no roles/users, so least privilege is applied at the connection
# level: the query engine opens the database file READ-ONLY (mode=ro). Any
# attempt to INSERT/UPDATE/DELETE/DROP through this engine fails, so even a
# future bug in a handler cannot modify data.
RO_ENGINE = create_engine("sqlite:///file:lab2.db?mode=ro&uri=true", future=True)


class Base(DeclarativeBase):
    pass


# --- Defence 2: ORM model (queries are parameterized by the ORM) ----------
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String)


# --- Defence 1: input validation / sanitization ---------------------------
# calc: only arithmetic characters, bounded length.
EXPR_RE = re.compile(r"^[0-9+\-*/%.()\s]{1,100}$")
# user name: letters/digits and a few safe punctuation chars, bounded length.
NAME_RE = re.compile(r"^[A-Za-z0-9 ._@-]{1,64}$")

# Allowed AST node types for the calculator (same allow-list as app_defended).
ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.USub, ast.UAdd,
)


@app.get("/calc")
def calc():
    expr = request.args.get("expr", "1+1")

    # Defence 1: validate/sanitize before parsing.
    if not EXPR_RE.fullmatch(expr):
        return jsonify({"error": "Invalid input"}), 400

    try:
        node = ast.parse(expr, mode="eval")
        if not all(isinstance(n, ALLOWED_NODES) for n in ast.walk(node)):
            raise ValueError("Disallowed expression")
        result = eval(compile(node, "<safe>", "eval"), {"__builtins__": {}}, {})
        return jsonify({"result": result})
    except Exception:
        return jsonify({"error": "Validation failed"}), 400


@app.get("/user")
def user():
    name = request.args.get("name", "").strip()

    # Defence 1: validate/sanitize the input.
    if not NAME_RE.fullmatch(name):
        return jsonify({"error": "Invalid name"}), 400

    # Defence 2 + 3: ORM query over a read-only engine. The ORM binds `name`
    # as a parameter, so injection payloads are treated as a literal value.
    with Session(RO_ENGINE) as session:
        rows = session.query(User).filter(User.name == name).all()
        return jsonify([{"id": r.id, "name": r.name, "email": r.email} for r in rows])


if __name__ == "__main__":
    app.run(port=5003)
