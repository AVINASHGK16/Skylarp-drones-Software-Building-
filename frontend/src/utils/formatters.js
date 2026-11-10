/**
 * Standardized Business Intelligence Formatting Utilities for Skylarp Drones.
 * Enforces Indian Currency formatting (Crores / Lakhs) and strict missing-value handling.
 */

/**
 * Format currency numbers into Indian Rupees (INR) format (Cr / Lakh).
 * Strict contract: Returns '—' for null, undefined, or NaN (never silently converts to ₹0).
 *
 * @param {number|null|undefined} val
 * @returns {string}
 */
export function formatCurrency(val) {
  if (val === undefined || val === null || (typeof val === 'number' && isNaN(val))) {
    return '—';
  }

  const num = Number(val);
  if (isNaN(num)) return '—';

  const absVal = Math.abs(num);
  const sign = num < 0 ? '-' : '';

  if (absVal >= 1e7) {
    return `${sign}₹${(absVal / 1e7).toFixed(2)} Cr`;
  }
  if (absVal >= 1e5) {
    return `${sign}₹${(absVal / 1e5).toFixed(2)} Lakh`;
  }
  return `${sign}₹${absVal.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

/**
 * Format numbers with en-IN comma separation.
 * Returns '—' for null or undefined.
 *
 * @param {number|null|undefined} val
 * @returns {string}
 */
export function formatCount(val) {
  if (val === undefined || val === null || (typeof val === 'number' && isNaN(val))) {
    return '—';
  }
  const num = Number(val);
  if (isNaN(num)) return '—';
  return num.toLocaleString('en-IN');
}


