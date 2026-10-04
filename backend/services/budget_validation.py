"""Validate the six shared monthly category budgets."""

from services.validation import MAX_AMOUNT, ValidationError

DEFAULT_BUDGETS = {'食費': 60000, '住まい': 90000, '日用品': 25000,
                   '交通': 25000, '娯楽': 30000, 'その他': 20000}


def normalize_budget(payload: object) -> dict[str, int]:
    categories = payload.get('categories') if isinstance(payload, dict) else None
    if not isinstance(categories, dict) or set(categories) != set(DEFAULT_BUDGETS):
        raise ValidationError('categories', '6つのカテゴリすべての予算を指定してください。')
    for name in DEFAULT_BUDGETS:
        value = categories[name]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_AMOUNT:
            raise ValidationError(f'categories.{name}', '0円から999,999,999円までの整数を入力してください。')
    return {name: categories[name] for name in DEFAULT_BUDGETS}
