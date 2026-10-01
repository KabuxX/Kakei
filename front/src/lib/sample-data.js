  const entries = [
    [28, '給与', '収入', 320000, 'income'],
    [27, '週末の買い物', '食費', 6840, 'expense'],
    [25, 'カフェとランチ', '食費', 2380, 'expense'],
    [24, '電車・バス', '交通', 4200, 'expense'],
    [22, '日用品のまとめ買い', '日用品', 5920, 'expense'],
    [20, '映画と外食', '娯楽', 7900, 'expense'],
    [18, 'スーパーマーケット', '食費', 9630, 'expense'],
    [15, '家賃', '住まい', 86000, 'expense'],
    [13, '書籍', '娯楽', 3100, 'expense'],
    [11, '食材の買い出し', '食費', 7340, 'expense'],
    [9, '電気・水道', '住まい', 12800, 'expense'],
    [7, '洗剤とティッシュ', '日用品', 3540, 'expense'],
    [5, '定期券', '交通', 10480, 'expense'],
    [3, '外食', '食費', 4860, 'expense'],
    [2, '週末の買い物', '食費', 8910, 'expense'],
    [1, 'フリマ売上', '収入', 12000, 'income'],
  ];
  const details = {
    1: { merchant: '青空スーパー', paymentMethod: 'credit_card', items: [{ name: '食材', amount: 3980 }, { name: '飲み物', amount: 1260 }, { name: 'お菓子', amount: 1600 }] },
    2: { merchant: '街角カフェ', paymentMethod: 'e_money', items: [{ name: 'ランチ', amount: 1680 }, { name: 'コーヒー', amount: 700 }] },
    3: { merchant: '東都交通', paymentMethod: 'e_money', items: [{ name: '電車運賃', amount: 2400 }, { name: 'バス運賃', amount: 1800 }] },
    4: { merchant: 'くらし用品店', paymentMethod: 'credit_card', items: [{ name: '洗濯洗剤', amount: 1980 }, { name: 'トイレットペーパー', amount: 1480 }, { name: '台所用品', amount: 2460 }] },
    5: { merchant: 'シネマ＆ダイニング', paymentMethod: 'credit_card', items: [{ name: '映画チケット', amount: 3600 }, { name: '夕食', amount: 4300 }] },
    6: { merchant: 'みどりスーパー', paymentMethod: 'e_money', items: [{ name: '青果', amount: 3480 }, { name: '肉・魚', amount: 4250 }, { name: '乳製品', amount: 1900 }] },
    7: { merchant: '住まい管理会社', paymentMethod: 'bank_account', items: [{ name: '家賃', amount: 86000 }] },
    8: { merchant: '駅前書店', paymentMethod: 'cash', items: [{ name: '書籍', amount: 2200 }, { name: '雑誌', amount: 900 }] },
    9: { merchant: '中央市場', paymentMethod: 'cash', items: [{ name: '野菜', amount: 2400 }, { name: '肉・魚', amount: 3590 }, { name: '調味料', amount: 1350 }] },
    10: { merchant: '公共料金センター', paymentMethod: 'bank_account', items: [{ name: '電気料金', amount: 7800 }, { name: '水道料金', amount: 5000 }] },
    11: { merchant: '生活用品マート', paymentMethod: 'e_money', items: [{ name: '洗剤', amount: 1680 }, { name: 'ティッシュ', amount: 1860 }] },
    12: { merchant: '東都交通', paymentMethod: 'credit_card', items: [{ name: '定期券', amount: 10480 }] },
    13: { merchant: 'まちの食堂', paymentMethod: 'cash', items: [{ name: '主菜', amount: 3200 }, { name: '飲み物', amount: 1660 }] },
    14: { merchant: '青空スーパー', paymentMethod: 'credit_card', items: [{ name: '食材', amount: 4120 }, { name: '日用品', amount: 2790 }, { name: 'おやつ', amount: 2000 }] },
  };

  function matchingDetails(record) {
    const match = /^sample-(\d+)$/.exec(record?.id);
    if (!match) return null;
    const index = Number(match[1]);
    const entry = entries[index];
    if (!entry || !details[index]) return null;
    if (record.title !== entry[1] || record.category !== entry[2] || record.amount !== entry[3] || record.type !== entry[4]) return null;
    return details[index];
  }

  function enrichSamples(records) {
    let changed = false;
    const enriched = records.map((record) => {
      const detail = matchingDetails(record);
      if (!detail) return record;
      const additions = {};
      if (!Object.hasOwn(record, 'merchant')) additions.merchant = detail.merchant;
      if (!Object.hasOwn(record, 'paymentMethod')) additions.paymentMethod = detail.paymentMethod;
      if (!Object.hasOwn(record, 'items')) additions.items = detail.items.map((item) => ({ ...item }));
      if (!Object.keys(additions).length) return record;
      changed = true;
      return { ...record, ...additions };
    });
    return changed ? enriched : records;
  }

  function createSampleTransactions(sampleMonth) {
    const month = `${sampleMonth.getFullYear()}-${String(sampleMonth.getMonth() + 1).padStart(2, '0')}`;
    const lastDay = new Date(sampleMonth.getFullYear(), sampleMonth.getMonth() + 1, 0).getDate();
    const records = entries.map(([day, title, category, amount, type], index) => ({
      id: `sample-${index}`, date: `${month}-${String(Math.min(day, lastDay)).padStart(2, '0')}`, title, category, amount, type,
    }));
    return enrichSamples(records);
  }

export { createSampleTransactions };
