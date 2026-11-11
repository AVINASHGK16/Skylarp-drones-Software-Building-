/**
 * API Client for Monday.com Business Intelligence Agent Backend.
 * Centralizes all HTTP communication with the FastAPI backend service.
 */

const RAW_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Strip any trailing slashes to avoid double-slash URL construction issues
const BASE_URL = RAW_BASE_URL.trim().replace(/\/+$/, '');

// Explicit Demo Mode configuration (default: false)
export const IS_DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

function buildApiUrl(endpoint) {
  return `${BASE_URL}/${endpoint.replace(/^\/+/, '')}`;
}

/**
 * Helper function to perform fetch requests with error handling.
 */
async function request(endpoint, options = {}) {
  const url = buildApiUrl(endpoint);
  const defaultHeaders = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };

  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  try {
    const response = await fetch(url, config);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage =
        errorData.detail ||
        errorData.message ||
        `HTTP Error ${response.status}: ${response.statusText}`;
      throw new Error(errorMessage);
    }
    return await response.json();
  } catch (error) {
    console.error(`API Error on [${options.method || 'GET'} ${endpoint}]:`, error);
    throw error;
  }
}

/**
 * Ask a strategic business question to the AI BI Agent.
 * Explicitly routes to /demo/ask when VITE_DEMO_MODE=true.
 * @param {string} question
 * @returns {Promise<{answer: string, dashboard_metrics: object, data_quality_notes: string[]}>}
 */
export async function askQuestion(question) {
  const endpoint = IS_DEMO_MODE ? '/demo/ask' : '/ask';
  return request(endpoint, {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
}

/**
 * Fetch pre-computed in-memory dashboard metrics.
 * Explicitly routes to /demo/metrics when VITE_DEMO_MODE=true.
 * @returns {Promise<{dashboard_metrics: object}>}
 */
export async function getMetrics() {
  const endpoint = IS_DEMO_MODE ? '/demo/metrics' : '/metrics';
  return request(endpoint, {
    method: 'GET',
  });
}

/**
 * Generate comprehensive executive leadership report.
 * Explicitly routes to /demo/leadership-report when VITE_DEMO_MODE=true.
 * @returns {Promise<{report: string, generated_at: string}>}
 */
export async function getLeadershipReport() {
  const endpoint = IS_DEMO_MODE ? '/demo/leadership-report' : '/leadership-report';
  return request(endpoint, {
    method: 'GET',
  });
}

/**
 * Check dataset source metadata.
 * Explicitly routes to /demo/data-status when VITE_DEMO_MODE=true.
 * @returns {Promise<object>}
 */
export async function getDataStatus() {
  const endpoint = IS_DEMO_MODE ? '/demo/data-status' : '/data-status';
  return request(endpoint, {
    method: 'GET',
  });
}
