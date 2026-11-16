"""Demo payment gateway.

A real shop would send the payment to Razorpay / Stripe / a bank here and get back
"approved" or "declined" plus a transaction reference. This demo decides itself:
  * a card number ending in 0000 is declined
  * a UPI id starting with "fail" is declined
  * everything else is approved
"""
import secrets
from dataclasses import dataclass


@dataclass
class GatewayResult:
    approved: bool
    transaction_ref: str | None
    message: str


def charge(method: str, amount: float, card_number: str | None, upi_id: str | None) -> GatewayResult:
    if method == "CARD":
        digits = "".join(ch for ch in (card_number or "") if ch.isdigit())
        if len(digits) < 12:
            return GatewayResult(False, None, "Please enter a valid card number")
        if digits.endswith("0000"):
            return GatewayResult(False, None, "Payment declined by bank. Please try another method.")
    if method == "UPI":
        if "@" not in (upi_id or ""):
            return GatewayResult(False, None, "Please enter a valid UPI ID, e.g. name@bank")
        if upi_id.lower().startswith("fail"):
            return GatewayResult(False, None, "Payment declined by bank. Please try another method.")
    return GatewayResult(True, "TXN-" + secrets.token_hex(6).upper(), f"Paid {amount:.2f}")
