/**
 * DNR-UI API Client - HTTP client for backend communication
 * Part of the Dazzle Native Runtime
 */

// =============================================================================
// API Client
// =============================================================================

export const apiClient = {
  baseUrl: '/api',

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
      const error = new Error(`HTTP ${response.status}`);
      error.status = response.status;
      try {
        error.data = await response.json();
      } catch {
        error.data = null;
      }
      throw error;
    }

    return response.json();
  },

  get(path, options) { return this.request('GET', path, null, options); },
  post(path, data, options) { return this.request('POST', path, data, options); },
  put(path, data, options) { return this.request('PUT', path, data, options); },
  patch(path, data, options) { return this.request('PATCH', path, data, options); },
  delete(path, options) { return this.request('DELETE', path, null, options); },

  // CRUD helpers for entities
  list(entity, params = {}) {
    const query = new URLSearchParams(params).toString();
    return this.get(`/${entity}${query ? '?' + query : ''}`);
  },
  read(entity, id) { return this.get(`/${entity}/${id}`); },
  create(entity, data) { return this.post(`/${entity}`, data); },
  update(entity, id, data) { return this.put(`/${entity}/${id}`, data); },
  remove(entity, id) { return this.delete(`/${entity}/${id}`); }
};

export default apiClient;
