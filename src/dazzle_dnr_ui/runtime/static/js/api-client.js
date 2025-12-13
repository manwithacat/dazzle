// @ts-check
/**
 * DNR-UI API Client - HTTP client for backend communication
 * Part of the Dazzle Native Runtime
 *
 * @module api-client
 */

// =============================================================================
// Type Definitions
// =============================================================================

/**
 * @typedef {Object} RequestOptions
 * @property {Record<string, string>} [headers] - Additional headers
 */

/**
 * @typedef {Object} ApiError
 * @property {number} status - HTTP status code
 * @property {any} data - Error response data
 * @property {string} message - Error message
 */

/**
 * @typedef {Object} PaginatedResponse
 * @property {Array<any>} items - List of items
 * @property {number} [total] - Total count
 * @property {number} [page] - Current page
 * @property {number} [page_size] - Items per page
 */

// =============================================================================
// API Client
// =============================================================================

/**
 * HTTP client for communicating with the DNR backend API.
 *
 * @example
 * // Basic usage
 * const tasks = await apiClient.list('tasks');
 * const task = await apiClient.create('tasks', { title: 'New Task' });
 * await apiClient.update('tasks', task.id, { completed: true });
 */
export const apiClient = {
  /** @type {string} Base URL for API requests */
  baseUrl: '/api',

  /**
   * Make an HTTP request.
   *
   * @param {string} method - HTTP method (GET, POST, PUT, PATCH, DELETE)
   * @param {string} path - API path (will be prefixed with baseUrl)
   * @param {any} [data] - Request body data (for POST, PUT, PATCH)
   * @param {RequestOptions} [options={}] - Additional request options
   * @returns {Promise<any>} Response data
   * @throws {ApiError} On HTTP error
   */
  async request(method, path, data = null, options = {}) {
    const url = `${this.baseUrl}${path}`;
    const fetchOptions = {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    };

    if (data && ['POST', 'PUT', 'PATCH'].includes(method)) {
      fetchOptions.body = JSON.stringify(data);
    }

    const response = await fetch(url, fetchOptions);

    if (!response.ok) {
      /** @type {ApiError & Error} */
      const error = /** @type {any} */ (new Error(`HTTP ${response.status}`));
      error.status = response.status;
      try {
        error.data = await response.json();
      } catch {
        error.data = null;
      }
      throw error;
    }

    // v0.14.2: Check content-type before parsing JSON
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      const text = await response.text();
      if (text.startsWith('<!DOCTYPE') || text.startsWith('<html')) {
        throw new Error(
          `API returned HTML instead of JSON for ${url}. ` +
          `Check that the backend is running and proxy is configured.`
        );
      }
      throw new Error(`Unexpected content type: ${contentType || 'unknown'}`);
    }

    return response.json();
  },

  /**
   * GET request.
   * @param {string} path - API path
   * @param {RequestOptions} [options] - Request options
   * @returns {Promise<any>}
   */
  get(path, options) { return this.request('GET', path, null, options); },

  /**
   * POST request.
   * @param {string} path - API path
   * @param {any} data - Request body
   * @param {RequestOptions} [options] - Request options
   * @returns {Promise<any>}
   */
  post(path, data, options) { return this.request('POST', path, data, options); },

  /**
   * PUT request.
   * @param {string} path - API path
   * @param {any} data - Request body
   * @param {RequestOptions} [options] - Request options
   * @returns {Promise<any>}
   */
  put(path, data, options) { return this.request('PUT', path, data, options); },

  /**
   * PATCH request.
   * @param {string} path - API path
   * @param {any} data - Request body
   * @param {RequestOptions} [options] - Request options
   * @returns {Promise<any>}
   */
  patch(path, data, options) { return this.request('PATCH', path, data, options); },

  /**
   * DELETE request.
   * @param {string} path - API path
   * @param {RequestOptions} [options] - Request options
   * @returns {Promise<any>}
   */
  delete(path, options) { return this.request('DELETE', path, null, options); },

  // =========================================================================
  // CRUD Helpers
  // =========================================================================

  /**
   * List entities with optional query parameters.
   * @param {string} entity - Entity name (e.g., 'tasks')
   * @param {Record<string, string>} [params={}] - Query parameters
   * @returns {Promise<PaginatedResponse|Array<any>>}
   */
  list(entity, params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.get(`/${entity}${query ? '?' + query : ''}`);
  },

  /**
   * Read a single entity by ID.
   * @param {string} entity - Entity name
   * @param {string} id - Entity ID
   * @returns {Promise<any>}
   */
  read(entity, id) { return this.get(`/${entity}/${id}`); },

  /**
   * Create a new entity.
   * @param {string} entity - Entity name
   * @param {any} data - Entity data
   * @returns {Promise<any>}
   */
  create(entity, data) { return this.post(`/${entity}`, data); },

  /**
   * Update an existing entity.
   * @param {string} entity - Entity name
   * @param {string} id - Entity ID
   * @param {any} data - Updated data
   * @returns {Promise<any>}
   */
  update(entity, id, data) { return this.put(`/${entity}/${id}`, data); },

  /**
   * Delete an entity.
   * @param {string} entity - Entity name
   * @param {string} id - Entity ID
   * @returns {Promise<any>}
   */
  remove(entity, id) { return this.delete(`/${entity}/${id}`); }
};

export default apiClient;
