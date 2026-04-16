# app.py - Main Flask server

from flask import Flask, render_template, request, jsonify, redirect, url_for
import uuid
from datetime import datetime
from db import execute_query, fetch_all, fetch_one
from fraud_engine import calculate_risk_score

app = Flask(__name__)
app.secret_key = "fraud_detection_2024"


@app.route("/")
def home():
    return redirect(url_for("checkout"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if request.method == "GET":
        return render_template("checkout.html")

    # ── Read form data (name, phone, city instead of user_id) ──
    full_name        = request.form.get("full_name", "Guest User")
    phone            = request.form.get("phone", "0000000000")
    city             = request.form.get("city", "Unknown")
    amount           = float(request.form.get("amount", 0))
    payment_method   = request.form.get("payment_method", "UPI")
    product_category = request.form.get("product_category", "clothing")
    quantity         = int(request.form.get("quantity", 1))
    shipping_city    = request.form.get("shipping_city", "")

    ip_address  = request.remote_addr or "127.0.0.1"
    user_agent  = request.headers.get("User-Agent", "")
    device_type = "mobile" if "Mobile" in user_agent else "desktop"
    now         = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Generate unique IDs for everything ──
    user_id        = "U" + str(uuid.uuid4())[:8]   # e.g. U-a1b2c3d4
    session_id     = str(uuid.uuid4())
    transaction_id = str(uuid.uuid4())

    # ── Step 1: Create new user in database automatically ──
    # Every person who checks out gets saved as a new user
    execute_query(
        """INSERT INTO users
           (user_id, full_name, email, phone, city, country, created_at, is_flagged)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (user_id,
         full_name,
         f"{phone}@checkout.com",   # dummy email since we dont ask for it
         phone,
         city,
         "India",
         now,
         0)
    )

    # ── Step 2: Create session in database ──
    execute_query(
        """INSERT INTO sessions
           (session_id, user_id, ip_address, device_type, browser,
            device_fingerprint, city_detected, started_at, risk_score, escalation_level)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (session_id, user_id, ip_address, device_type,
         user_agent[:40], f"fp_{session_id[:8]}",
         city, now, 0.00, "LOW")
    )

    # ── Step 3: Create transaction in database ──
    execute_query(
        """INSERT INTO transactions
           (transaction_id, session_id, user_id, amount, currency,
            payment_method, product_category, quantity,
            shipping_city, billing_city, status, initiated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (transaction_id, session_id, user_id, amount, "INR",
         payment_method, product_category, quantity,
         shipping_city, city, "PENDING", now)
    )

    # ── Step 4: Run fraud scoring ──
    # account_age = 0 because this is a brand new account
    result = calculate_risk_score(
        {
            "session_id":                session_id,
            "ip_address":                ip_address,
            "city_detected":             city,
            "account_age_days":          0,      # new user = 0 days old = more suspicious
            "checkout_duration_seconds": 20      # simulated checkout speed
        },
        {
            "amount":           amount,
            "quantity":         quantity,
            "product_category": product_category,
            "shipping_city":    shipping_city
        }
    )

    decision = result["decision"]

    # ── Step 5: Update transaction status based on decision ──
    status_map = {
        "APPROVE": "SUCCESS",
        "STEP_UP": "SUCCESS",
        "FLAG":    "PENDING",
        "BLOCK":   "BLOCKED"
    }
    execute_query(
        "UPDATE transactions SET status=%s WHERE transaction_id=%s",
        (status_map[decision], transaction_id)
    )

    # ── Step 6: Save fraud decision ──
    execute_query(
        """INSERT INTO fraud_decisions
           (decision_id, transaction_id, session_id, decision, final_score, decided_at)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (str(uuid.uuid4()), transaction_id, session_id,
         decision, result["risk_score"], now)
    )

    # ── Step 7: Send result back to browser ──
    messages = {
        "APPROVE": "Payment successful! Your order has been placed.",
        "STEP_UP": "Please verify with the OTP sent to your phone.",
        "FLAG":    "Your order is under review. We will confirm shortly.",
        "BLOCK":   "Transaction declined. Please contact support."
    }

    return jsonify({
        "decision":         decision,
        "risk_score":       result["risk_score"],
        "escalation_level": result["escalation_level"],
        "message":          messages[decision],
        "user_name":        full_name
    })


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html",
        total_sessions     = fetch_one("SELECT COUNT(*) AS c FROM sessions")["c"],
        total_transactions = fetch_one("SELECT COUNT(*) AS c FROM transactions")["c"],
        total_blocked      = fetch_one("SELECT COUNT(*) AS c FROM fraud_decisions WHERE decision='BLOCK'")["c"],
        total_flagged      = fetch_one("SELECT COUNT(*) AS c FROM fraud_decisions WHERE decision='FLAG'")["c"],
        recent_decisions   = fetch_all("""
            SELECT fd.decision, fd.final_score, fd.decided_at,
                   fd.reviewed_by, t.amount, t.payment_method,
                   t.product_category, u.full_name
            FROM fraud_decisions fd
            JOIN transactions t ON fd.transaction_id = t.transaction_id
            JOIN users u        ON t.user_id = u.user_id
            ORDER BY fd.decided_at DESC LIMIT 20
        """),
        recent_sessions    = fetch_all("""
            SELECT s.ip_address, s.device_type, s.city_detected,
                   s.risk_score, s.escalation_level, s.started_at,
                   u.full_name
            FROM sessions s
            JOIN users u ON s.user_id = u.user_id
            ORDER BY s.started_at DESC LIMIT 20
        """),
        recent_signals     = fetch_all("""
            SELECT rs.signal_source, rs.signal_name,
                   rs.score_contribution, rs.details, u.full_name
            FROM risk_signals rs
            JOIN sessions s ON rs.session_id = s.session_id
            JOIN users u    ON s.user_id = u.user_id
            ORDER BY rs.triggered_at DESC LIMIT 20
        """)
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)