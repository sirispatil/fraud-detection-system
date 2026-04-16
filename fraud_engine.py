# fraud_engine.py

import os
import uuid
from datetime import datetime
import joblib
from db import execute_query

# --------------------------------------------------------------------------
# RULE CONFIG
# --------------------------------------------------------------------------
FRAUD_IP_PREFIXES = ["185.220", "45.227", "194.165", "91.108", "5.188"]
HIGH_RISK_CATEGORIES = ["electronics", "jewelry"]

# --------------------------------------------------------------------------
# LOAD ML MODEL (FIXED PATH)
# --------------------------------------------------------------------------
MODEL = None
MODEL_PATH = os.path.join(os.path.dirname(__file__), "model", "model.pkl")

if os.path.exists(MODEL_PATH):
    MODEL = joblib.load(MODEL_PATH)
    print("✅ ML model loaded successfully.")
else:
    print("⚠️ Warning: model.pkl not found. ML scoring skipped.")


# ==========================================================================
# MAIN FUNCTION
# ==========================================================================
def calculate_risk_score(session_data, transaction_data):

    total_score = 0
    signals_fired = []

    session_id = session_data.get("session_id")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ip = session_data.get("ip_address", "")
    account_city = session_data.get("city_detected", "").lower()
    shipping_city = transaction_data.get("shipping_city", "").lower()

    quantity = transaction_data.get("quantity", 1)
    amount = float(transaction_data.get("amount", 0))
    account_age = session_data.get("account_age_days", 999)
    product_cat = transaction_data.get("product_category", "")
    hour = datetime.now().hour

    # ----------------------------------------------------------------------
    # RULE 1: Fraud IP
    # ----------------------------------------------------------------------
    for prefix in FRAUD_IP_PREFIXES:
        if ip.startswith(prefix):
            score = 35
            total_score += score
            signals_fired.append({
                "signal_source": "RULE",
                "signal_name": "known_fraud_ip_range",
                "score": score,
                "details": f"IP {ip} flagged"
            })
            break

    # ----------------------------------------------------------------------
    # RULE 2: Odd Hour
    # ----------------------------------------------------------------------
    if 1 <= hour <= 4:
        score = 20
        total_score += score
        signals_fired.append({
            "signal_source": "RULE",
            "signal_name": "odd_hour",
            "score": score,
            "details": f"{hour} AM transaction"
        })

    # ----------------------------------------------------------------------
    # RULE 3: City mismatch
    # ----------------------------------------------------------------------
    if account_city and shipping_city and account_city != shipping_city:
        score = 15
        total_score += score
        signals_fired.append({
            "signal_source": "RULE",
            "signal_name": "city_mismatch",
            "score": score,
            "details": f"{account_city} vs {shipping_city}"
        })

    # ----------------------------------------------------------------------
    # RULE 4: High quantity
    # ----------------------------------------------------------------------
    if quantity >= 5:
        score = 25
        total_score += score
        signals_fired.append({
            "signal_source": "RULE",
            "signal_name": "bulk_order",
            "score": score,
            "details": f"Quantity {quantity}"
        })

    # ----------------------------------------------------------------------
    # RULE 5: New account high amount
    # ----------------------------------------------------------------------
    if account_age < 30 and amount > 10000:
        score = 22
        total_score += score
        signals_fired.append({
            "signal_source": "RULE",
            "signal_name": "new_account_high_amount",
            "score": score,
            "details": f"{account_age} days, ₹{amount}"
        })

    # ----------------------------------------------------------------------
    # RULE 6: High risk category
    # ----------------------------------------------------------------------
    if product_cat in HIGH_RISK_CATEGORIES and amount > 20000:
        score = 10
        total_score += score
        signals_fired.append({
            "signal_source": "RULE",
            "signal_name": "high_risk_category",
            "score": score,
            "details": product_cat
        })

    # ----------------------------------------------------------------------
    # ML MODEL (FIXED)
    # ----------------------------------------------------------------------
    if MODEL is not None:
        try:
            customer_age = 25  # dummy (can improve later)

            features = [[
                amount,
                quantity,
                customer_age,
                account_age,
                hour
            ]]

            prob = MODEL.predict_proba(features)[0][1]
            ml_score = round(prob * 30, 2)

            total_score += ml_score

            signals_fired.append({
                "signal_source": "ML",
                "signal_name": "ml_prediction",
                "score": ml_score,
                "details": f"Probability {prob:.2f}"
            })

        except Exception as e:
            print("ML ERROR:", e)

    # ----------------------------------------------------------------------
    # BIO SIGNAL
    # ----------------------------------------------------------------------
    checkout_time = session_data.get("checkout_duration_seconds", 120)

    if checkout_time < 30:
        score = 12
        total_score += score
        signals_fired.append({
            "signal_source": "BIO",
            "signal_name": "fast_checkout",
            "score": score,
            "details": f"{checkout_time}s"
        })

    # ----------------------------------------------------------------------
    # FINAL SCORE
    # ----------------------------------------------------------------------
    total_score = min(round(total_score, 2), 100)

    if total_score >= 86:
        decision = "BLOCK"
        escalation = "BLOCK"
    elif total_score >= 61:
        decision = "FLAG"
        escalation = "HIGH"
    elif total_score >= 31:
        decision = "STEP_UP"
        escalation = "MEDIUM"
    else:
        decision = "APPROVE"
        escalation = "LOW"

    # ----------------------------------------------------------------------
    # SAVE SIGNALS
    # ----------------------------------------------------------------------
    for sig in signals_fired:
        execute_query(
            """INSERT INTO risk_signals
               (signal_id, session_id, signal_source, signal_name,
                score_contribution, triggered_at, details)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (str(uuid.uuid4()), session_id,
             sig["signal_source"], sig["signal_name"],
             sig["score"], now, sig["details"])
        )

    # ----------------------------------------------------------------------
    # UPDATE SESSION
    # ----------------------------------------------------------------------
    execute_query(
        """UPDATE sessions
           SET risk_score=%s, escalation_level=%s, ended_at=%s
           WHERE session_id=%s""",
        (total_score, escalation, now, session_id)
    )

    return {
        "risk_score": total_score,
        "decision": decision,
        "escalation_level": escalation,
        "signals_fired": signals_fired
    }