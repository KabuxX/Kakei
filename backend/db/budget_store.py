"""Category budget queries within a caller-owned SQLite transaction."""

from services.budget_validation import DEFAULT_BUDGETS


def ensure_budget_schema(connection) -> None:
    connection.execute('''CREATE TABLE IF NOT EXISTS category_budgets (
        category TEXT PRIMARY KEY,
        amount INTEGER NOT NULL CHECK(typeof(amount) = 'integer' AND amount BETWEEN 0 AND 999999999)
    )''')
    connection.executemany('INSERT OR IGNORE INTO category_budgets(category, amount) VALUES (?, ?)',
                           DEFAULT_BUDGETS.items())


def read_budget(connection) -> dict[str, int]:
    return {row[0]: row[1] for row in connection.execute('SELECT category, amount FROM category_budgets')}


def write_budget(connection, categories: dict[str, int]) -> None:
    connection.executemany('UPDATE category_budgets SET amount = ? WHERE category = ?',
                           ((amount, name) for name, amount in categories.items()))
