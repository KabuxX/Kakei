"""Validation shared by imports and new transaction writes."""

from typing import Optional

from transaction_datetime import parse_transaction_datetime


MAX_AMOUNT = 999_999_999
EXPENSE_CATEGORIES = frozenset(("食費", "住まい", "日用品", "交通", "娯楽", "その他"))
PAYMENT_METHODS = frozenset(("cash", "credit_card", "e_money", "bank_account"))


class ValidationError(ValueError):
    def __init__(self, field: Optional[str], message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def _text(value: object, field: str, *, limit: Optional[int] = None) -> str:
    if not isinstance(value, str):
        raise ValidationError(field, "文字列を入力してください。")
    result = value.strip()
    if not result or (limit is not None and len(result) > limit):
        raise ValidationError(field, "1文字以上の有効な文字列を入力してください。")
    return result


def _amount(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_AMOUNT:
        raise ValidationError(field, "1円から999,999,999円までの整数を入力してください。")
    return value


def _items(value: object, amount: int, *, import_mode: bool) -> list:
    if not isinstance(value, list):
        if import_mode:
            return []
        raise ValidationError("items", "品目の形式が正しくありません。")
    normalized = []
    for item in value:
        try:
            if not isinstance(item, dict):
                raise ValidationError("items", "品目の形式が正しくありません。")
            name = _text(item.get("name"), "items", limit=None if import_mode else 60)
            item_amount = _amount(item.get("amount"), "items")
            normalized.append({"name": item["name"] if import_mode else name, "amount": item_amount})
        except ValidationError:
            if import_mode:
                return []
            raise
    if normalized and sum(item["amount"] for item in normalized) != amount:
        if import_mode:
            return []
        raise ValidationError("items", "品目の合計と取引金額が一致しません。")
    return normalized


def normalize_transaction(payload: object, *, import_mode: bool = False) -> dict:
    """Return a safe transaction with the field names used by the browser."""
    if not isinstance(payload, dict):
        raise ValidationError(None, "取引はオブジェクトで指定してください。")
    if import_mode:
        transaction_id = _text(payload.get("id"), "id")
    elif "id" in payload:
        raise ValidationError("id", "IDはサーバーが生成します。")

    title = _text(payload.get("title"), "title", limit=None if import_mode else 60)
    try:
        date_value, time_estimated = parse_transaction_datetime(
            payload.get("date"), allow_date_only=import_mode
        )
    except ValueError as error:
        raise ValidationError("date", "正しい日時を入力してください。") from error

    kind = payload.get("type")
    if kind not in ("income", "expense"):
        raise ValidationError("type", "収入または支出を選んでください。")
    category = _text(payload.get("category"), "category")
    if not import_mode:
        allowed = {"収入"} if kind == "income" else EXPENSE_CATEGORIES
        if category not in allowed:
            raise ValidationError("category", "カテゴリを選んでください。")
    amount = _amount(payload.get("amount"), "amount")

    result = {"title": title, "date": date_value, "type": kind,
              "category": category, "amount": amount,
              "timeEstimated": time_estimated}
    if import_mode:
        result["id"] = transaction_id
    if kind == "expense":
        if import_mode:
            merchant = payload.get("merchant")
            result["merchant"] = merchant.strip() if isinstance(merchant, str) and merchant.strip() else None
            payment = payload.get("paymentMethod")
            result["paymentMethod"] = payment if isinstance(payment, str) and payment in PAYMENT_METHODS else None
        else:
            result["merchant"] = _text(payload.get("merchant"), "merchant", limit=60)
            payment = payload.get("paymentMethod")
            if not isinstance(payment, str) or payment not in PAYMENT_METHODS:
                raise ValidationError("paymentMethod", "支払方法を選んでください。")
            result["paymentMethod"] = payment
        result["items"] = _items(payload.get("items", []), amount, import_mode=import_mode)
    return result
