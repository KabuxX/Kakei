"""Allocate printed receipt amounts using integer arithmetic, without changing evidence."""

def allocate(total, weights):
    """Largest remainder; ties follow receipt order. Inputs are validated by caller."""
    denominator = sum(weights)
    parts = [total * weight // denominator for weight in weights]
    order = sorted(range(len(weights)), key=lambda i: (-(total * weights[i] % denominator), i))
    for i in order[:total - sum(parts)]:
        parts[i] += 1
    return parts


def calculate_receipt(value):
    groups = value.get('tax_groups') or []
    items = value.get('items') or []
    # Older extractions do not contain evidence for tax allocation.
    if not groups and not any(item.get('tax_group') for item in items):
        return None, None
    issues = []
    result = {'method':'printed-tax-largest-remainder-v1', 'rows':[], 'issues':issues}
    def fail(message):
        issues.append(message)
        return result, None
    if value.get('currency') != 'JPY':
        return fail('自動計算は日本円のレシートに対応しています。')
    if not items or any(not 0 < item['amount'] <= 999999999 for item in items):
        return fail('品目の印字金額を確認してください。ゼロ円・負の品目は自動配分できません。')
    by_id = {group['id']:group for group in groups}
    if len(by_id) != len(groups) or any(item.get('tax_group') not in by_id for item in items):
        return fail('品目の税区分を特定できません。原本で税抜・税込・非課税を確認してください。')
    taxes = [0] * len(items)
    for group in groups:
        indexes = [i for i,item in enumerate(items) if item.get('tax_group') == group['id']]
        subtotal = sum(items[i]['amount'] for i in indexes)
        if not indexes or group['subtotal'] != subtotal:
            return fail('税区分ごとの品目合計と印字小計が一致しません。')
        basis,rate,tax = group['basis'],group['rate'],group['tax']
        if basis == 'exempt':
            if rate not in (None,0) or tax not in (None,0):
                return fail('非課税区分の税率・税額を確認してください。')
        elif basis in ('exclusive','inclusive') and rate in (8,10):
            if basis == 'exclusive' and tax is None:
                return fail('税抜小計に対応する印字税額が読み取れません。')
            if tax is not None:
                # Accept common floor/nearest/ceil rounding, but never invent a rate or tax.
                denominator = 100 if basis == 'exclusive' else 100 + rate
                numerator = subtotal * rate
                if tax < numerator // denominator or tax > (numerator + denominator - 1) // denominator:
                    return fail('印字税額と税率・小計が整合しません。原本を確認してください。')
            if basis == 'exclusive':
                for i,part in zip(indexes,allocate(tax,[items[i]['amount'] for i in indexes])):
                    taxes[i] = part
        else:
            return fail('税区分・税率が不明です。原本を確認してください。')
    gross = [item['amount'] + taxes[i] for i,item in enumerate(items)]
    total = sum(gross)
    if total != value.get('total'):
        return fail('計算した税込合計と印字合計が一致しません。')
    discount = value.get('discount') or 0
    paid = value.get('paid_total')
    if discount < 0 or discount >= total or (discount and paid is None):
        return fail('還元・値引額と実支払額を確認してください。')
    if paid is None:
        paid = total
    if total - discount != paid:
        return fail('税込合計・還元額・実支払額が一致しません。差額は自動で補いません。')
    discounts = allocate(discount, gross)
    net = [amount - discounts[i] for i,amount in enumerate(gross)]
    if any(not 0 < amount <= 999999999 for amount in net) or not 0 < paid <= 999999999:
        return fail('配分後に保存できない金額が生じます。品目を確認してください。')
    result.update(grossTotal=total, discountTotal=discount, paidTotal=paid,
                  rows=[{'name':item['name'],'printed':item['amount'],
                         'basis':by_id[item['tax_group']]['basis'],'rate':by_id[item['tax_group']]['rate'],
                         'addedTax':taxes[i],'gross':gross[i],'discount':discounts[i],'net':net[i]}
                        for i,item in enumerate(items)])
    return result, {'amount':paid,'items':[{'name':item['name'],'amount':net[i]} for i,item in enumerate(items)]}
