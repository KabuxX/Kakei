import transactions from '../data/september-transactions.json';

function createSampleTransactions() {
  return structuredClone(transactions);
}

export { createSampleTransactions };
