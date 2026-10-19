# Lab 2 — Injection Vulnerabilities: Eval Abuse & SQL Injection

Educational security lab. A deliberately vulnerable Flask app is exploited,
then a hardened version is shown to block the same attacks.

## Files

| File | Purpose |
|---|---|
| `seed_db.py` | Creates `lab2.db` with sample users (alice, bob, charlie) |
| `app_vulnerable.py` | Vulnerable app — port **5001** |
| `app_defended.py` | Hardened app — port **5002** |
| `exploit_calc.py` | Eval-abuse / RCE exploit (`--defended` to target the hardened app) |
| `exploit_sqli.py` | SQL-injection exploit (`--defended` to target the hardened app) |

## How to run (Codespace / local)

```bash
pip install flask requests
python seed_db.py            # seed the database
python app_vulnerable.py &   # vulnerable, port 5001
python app_defended.py &     # defended,  port 5002

# exploits (omit --defended to hit the vulnerable app)
python exploit_calc.py
python exploit_calc.py --defended
python exploit_sqli.py
python exploit_sqli.py --defended
```

> Manual curl note: in a URL query string `+` means space, so URL-encode it
> (`%2B`) or use `curl -G ... --data-urlencode "expr=2+3"`.

---

## A. Eval Abuse (Calculator Endpoint)

- **Endpoint:** `GET /calc?expr=<expression>`
- **Vulnerable code:** `result = eval(expr)` on untrusted input
- **Payload:** `__import__('os').popen('echo PWNED').read()`

| Target | Status | Response | Outcome |
|---|---|---|---|
| Vulnerable (5001) | `200` | `{"result":"PWNED\n"}` | Command executed — **remote code execution** |
| Defended (5002) | `400` | `{"error":"Validation failed"}` | **Blocked** before any evaluation |

**Why it works (vulnerable):** `eval()` executes arbitrary Python, so the
payload imports `os` and runs a shell command; `popen().read()` returns the
command's stdout in the HTTP response.

## B. SQL Injection (User Lookup Endpoint)

- **Endpoint:** `GET /user?name=<name>`
- **Vulnerable code:** `f"SELECT id, name, email FROM users WHERE name = '{name}'"`
- **Payload:** `' OR '1'='1' -- `

| Target | Status | Response | Outcome |
|---|---|---|---|
| Vulnerable (5001) | `200` | all 3 rows (alice, bob, charlie) | **Filter/auth bypass** — full table disclosed |
| Defended (5002) | `200` | `[]` | **Blocked** — payload treated as a literal name |

**Why it works (vulnerable):** the input is concatenated into the query, so
`WHERE name = '' OR '1'='1' -- '` is always true and the trailing `--`
comments out the rest. Every row is returned.

---

## C. Remediation (verified in `app_defended.py`)

### 1. Securing eval — AST allow-list (not `ast.literal_eval`)

```python
node = ast.parse(expr, mode="eval")
allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
           ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod)
if not all(isinstance(n, allowed) for n in ast.walk(node)):
    raise ValueError("Disallowed expression")
result = eval(compile(node, "<safe>", "eval"), {"__builtins__": {}}, {})
```

Parse the expression, walk every node against an allow-list of arithmetic
node types, and evaluate with empty `__builtins__`. Any `Call`/`Attribute`
(e.g. `__import__(...)`, `popen`) is rejected before execution, while real
arithmetic still works (`2+3` → `5`).

> **Note:** `ast.literal_eval("2+3")` raises `ValueError` — it evaluates only
> *literals*, not arithmetic, so it breaks the calculator. The AST allow-list
> above is the correct fix.

### 2. Securing SQL — parameterized query

```python
rows = conn.execute(
    "SELECT id, name, email FROM users WHERE name = ?", (name,)
).fetchall()
```

The `?` placeholder binds the input as data; the driver never interprets it
as SQL, so injection payloads match no user.

### 3. Secure practices (defense in depth)

- Validate and sanitize all inputs (type, length, allowed characters).
- Use an ORM (e.g. SQLAlchemy) so queries are parameterized by default.
- Apply least-privilege DB credentials (e.g. a read-only account for lookups).
- Fail closed with generic error messages (no stack traces to the client).

---

## Summary: before → after

| Attack | Vulnerable (5001) | Defended (5002) |
|---|---|---|
| Calc RCE | `200` `{"result":"PWNED\n"}` | `400` validation failed |
| SQL injection | `200` 3 users leaked | `200` `[]` |

Both vulnerabilities are fully mitigated in `app_defended.py`, confirmed by
running the exploit scripts against both servers.
