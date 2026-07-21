/**
 * API Client for Monday.com Business Intelligence Agent Backend.
 * Centralizes all HTTP communication with the FastAPI backend service.
 */

const RAW_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Strip any trailing slashes to avoid double-slash URL construction issues
const BASE_URL = RAW_BASE_URL.trim().replace(/\/+$/, '');

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
 * Check backend connection health status.
 * Executes GET /health and evaluates if the FastAPI server is reachable.
 * @returns {Promise<{status: string}>}
 */
export async function checkHealth() {
  const response = await fetch(buildApiUrl('/health'), {
    method: 'GET',
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Health check failed with HTTP ${response.status}`);
  }

  return response.json();
}

/**
 * Ask a strategic business question to the AI BI Agent.
 * @param {string} question
 * @returns {Promise<{answer: string, dashboard_metrics: object, data_quality_notes: string[]}>}
 */
export async function askQuestion(question) {
  return request('/ask', {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
}

/**
 * Fetch pre-computed in-memory dashboard metrics.
 * @returns {Promise<{dashboard_metrics: object}>}
 */
export async function getMetrics() {
  return request('/metrics', {
    method: 'GET',
  });
}

/**
 * Generate comprehensive executive leadership report.
 * @returns {Promise<{report: string, generated_at: string}>}
 */
export async function getLeadershipReport() {
  return request('/leadership-report', {
    method: 'GET',
  });
}
