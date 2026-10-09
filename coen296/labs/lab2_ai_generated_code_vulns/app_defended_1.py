from flask import Flask, request, jsonify
import ast
import operator
import sqlite3

app = Flask(__name__)

def get_db():
    conn = sqlite3.connect("lab2.db")
    conn.row_factory = sqlite3.Row
    return conn

# --- Safe arithmetic evaluator (no eval / no compile / no code execution) ---

# Explicit allow-list of binary and unary operators.
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Cap exponent so `expr=9**9**9` can't hang the server (DoS).
_MAX_POW_EXPONENT = 100

def _eval_node(node):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):          # numeric literal (3.8+)
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("Only numbers are allowed")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POW_EXPONENT:
            raise ValueError("Exponent too large")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    # Anything else (Name, Call, Attribute, Import, etc.) is rejected.
    raise ValueError("Disallowed expression")

def safe_eval(expr: str):
    tree = ast.parse(expr, mode="eval")
    return _eval_node(tree)

@app.get("/calc")
def calc():
    expr = request.args.get("expr", "1+1")
    try:
        return jsonify({"result": safe_eval(expr)})
    except ZeroDivisionError:
        return jsonify({"error": "Division by zero"}), 400
    except Exception:
        return jsonify({"error": "Validation failed"}), 400

@app.get("/user")
def user():
    name = request.args.get("name", "")
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, email FROM users WHERE name = ?", (name,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

if __name__ == "__main__":
    app.run(port=5002)
