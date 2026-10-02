export function dateTimeLocalValue(date = new Date()) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
    throw new TypeError('A valid Date is required');
  }
  const pad = (value) => String(value).padStart(2, '0');
  return `${String(date.getFullYear()).padStart(4, '0')}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function assignEstimatedTransactionDatetimes(records) {
  const result = records.map((record) => ({ ...record }));
  const groups = new Map();
  for (const [index, record] of records.entries()) {
    if (typeof record.id !== 'string') throw new TypeError('Transaction IDs must be strings');
    if (/^\d{4}-\d{2}-\d{2}$/.test(record.date)) {
      if (!isValidTransactionDateTime(`${record.date}T00:00`)) throw new TypeError('Invalid transaction date');
      if (!groups.has(record.date)) groups.set(record.date, []);
      groups.get(record.date).push({ id: record.id, index });
    } else {
      if (!isValidTransactionDateTime(record.date)) throw new TypeError('Invalid transaction datetime');
      result[index].timeEstimated = false;
    }
  }

  for (const [day, rows] of groups) {
    const count = rows.length;
    if (count > 1440) throw new RangeError(`More than 1440 transactions on ${day}`);
    rows.sort((left, right) => (left.id < right.id ? -1 : left.id > right.id ? 1 : 0));
    for (const [position, row] of rows.entries()) {
      const minuteOfDay = count === 1
        ? 12 * 60
        : count <= 840
          ? 8 * 60 + Math.floor(((position + 1) * 840) / (count + 1))
          : Math.floor(((position + 1) * 1440) / (count + 1));
      const hour = Math.floor(minuteOfDay / 60);
      const minute = minuteOfDay % 60;
      result[row.index].date = `${day}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
      result[row.index].timeEstimated = true;
    }
  }
  return result;
}

export function transactionCalendarDate(value) {
  return typeof value === 'string' ? value.slice(0, 10) : '';
}

export function transactionMonthKey(value) {
  return typeof value === 'string' ? value.slice(0, 7) : '';
}

export function isValidTransactionDateTime(value) {
  if (typeof value !== 'string') return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match || match[0] !== value) return false;
  const [, yearText, monthText, dayText, hourText, minuteText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  if (year < 1 || month < 1 || month > 12 || hour > 23 || minute > 59) return false;
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day >= 1 && day <= daysInMonth[month - 1];
}

export function formatTransactionDate(value) {
  const date = transactionCalendarDate(value);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) return typeof value === 'string' ? value : '';
  const [, year, month, day] = match;
  const formatted = `${Number(year)}年${Number(month)}月${Number(day)}日`;
  return isValidTransactionDateTime(value) ? `${formatted} ${value.slice(11, 16)}` : formatted;
}
