"""
Real-time client JavaScript generator for DNR-UI.

Generates JavaScript code for WebSocket communication, presence, and optimistic updates.

NOTE: The JavaScript has been modularized into static/js/realtime.js.
This module now loads from that file via js_loader.py.
The REALTIME_CLIENT_JS variable is kept for backward compatibility.
"""

from __future__ import annotations


# =============================================================================
# Runtime Loading
# =============================================================================

def _load_realtime_js() -> str:
    """
    Load the realtime client JavaScript from the modular file.

    Falls back to the inline version if the loader is not available.
    """
    try:
        from dazzle_dnr_ui.runtime.js_loader import load_js_module
        # Load and wrap in IIFE for non-module usage
        source = load_js_module("realtime.js")
        return _wrap_in_iife(source)
    except (ImportError, FileNotFoundError):
        # Fall back to inline version
        return _REALTIME_CLIENT_JS_INLINE


def _wrap_in_iife(source: str) -> str:
    """Wrap ES module source in an IIFE for non-module browsers."""
    lines = source.split('\n')
    result = [
        '/**',
        ' * DNR-UI Realtime Client',
        ' * Provides WebSocket communication, presence, and optimistic updates.',
        ' * Version: 0.4.0 (Week 13-14)',
        ' */',
        "(function(global) {",
        "  'use strict';",
        "",
    ]

    for line in lines:
        stripped = line.strip()
        # Skip import/export statements
        if stripped.startswith('import '):
            continue
        if stripped.startswith('export '):
            line = line.replace('export ', '', 1)
        if stripped.startswith('export default'):
            continue
        if line.strip():
            result.append('  ' + line)
        else:
            result.append('')

    # Add exports
    result.extend([
        '',
        '  // Export',
        '  const Realtime = {',
        '    RealtimeClient,',
        '    OptimisticManager,',
        '    PresenceManager,',
        '    EntitySync,',
        '    createRealtimeClient',
        '  };',
        '',
        '  if (global.DNR) {',
        '    global.DNR.Realtime = Realtime;',
        '    global.DNR.createRealtimeClient = createRealtimeClient;',
        '  }',
        '  global.DNRRealtime = Realtime;',
        '',
        "})(typeof window !== 'undefined' ? window : global);",
    ])

    return '\n'.join(result)


# =============================================================================
# Realtime Client JavaScript (Inline Fallback)
# =============================================================================

# This is kept for backward compatibility and as a fallback if the modular
# file is not available. The canonical source is now in static/js/realtime.js
_REALTIME_CLIENT_JS_INLINE = '''
/**
 * DNR-UI Realtime Client
 * Provides WebSocket communication, presence, and optimistic updates.
 * Version: 0.4.0 (Week 13-14)
 */
(function(global) {
  'use strict';

  // ==========================================================================
  // Realtime Client
  // ==========================================================================

  class RealtimeClient {
    constructor(url, options = {}) {
      this.url = url;
      this.options = {
        reconnectInterval: 1000,
        maxReconnectAttempts: 10,
        heartbeatInterval: 25000,
        debug: false,
        ...options
      };

      this.ws = null;
      this.connected = false;
      this.connectionId = null;
      this.userId = null;
      this.subscriptions = new Map();
      this.pendingRequests = new Map();
      this.reconnectAttempts = 0;
      this.heartbeatTimer = null;
      this.listeners = new Map();

      // Use DNR signals if available
      if (global.DNR && global.DNR.createSignal) {
        const [connSignal, setConnSignal] = global.DNR.createSignal(false);
        this.connectedSignal = connSignal;
        this._setConnected = setConnSignal;
      }
    }

    // ========================================================================
    // Connection Management
    // ========================================================================

    connect(token = null) {
      return new Promise((resolve, reject) => {
        const url = token ? `${this.url}?token=${encodeURIComponent(token)}` : this.url;

        try {
          this.ws = new WebSocket(url);
        } catch (error) {
          reject(error);
          return;
        }

        this.ws.onopen = () => {
          this._log('Connected to realtime server');
          this.reconnectAttempts = 0;
          this._startHeartbeat();
        };

        this.ws.onclose = (event) => {
          this._log('Connection closed', event.code, event.reason);
          this._onDisconnect();
          this._attemptReconnect();
        };

        this.ws.onerror = (error) => {
          this._log('WebSocket error', error);
          reject(error);
        };

        this.ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            this._handleMessage(message);

            // Resolve connect promise when we receive connected message
            if (message.type === 'connected') {
              this.connected = true;
              this.connectionId = message.payload?.connectionId;
              this.userId = message.payload?.userId;
              if (this._setConnected) this._setConnected(true);
              resolve(this);
            }
          } catch (e) {
            this._log('Failed to parse message', e);
          }
        };
      });
    }

    disconnect() {
      this._stopHeartbeat();
      if (this.ws) {
        this.ws.close(1000, 'Client disconnect');
        this.ws = null;
      }
      this._onDisconnect();
    }

    _onDisconnect() {
      this.connected = false;
      this.connectionId = null;
      if (this._setConnected) this._setConnected(false);
      this._stopHeartbeat();
      this._emit('disconnect');
    }

    _attemptReconnect() {
      if (this.reconnectAttempts >= this.options.maxReconnectAttempts) {
        this._log('Max reconnect attempts reached');
        this._emit('reconnect_failed');
        return;
      }

      this.reconnectAttempts++;
      const delay = this.options.reconnectInterval * Math.pow(2, this.reconnectAttempts - 1);

      this._log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

      setTimeout(() => {
        if (!this.connected) {
          this.connect().catch(() => {});
        }
      }, delay);
    }

    _startHeartbeat() {
      this._stopHeartbeat();
      this.heartbeatTimer = setInterval(() => {
        this._send({ type: 'ping', timestamp: Date.now() });
      }, this.options.heartbeatInterval);
    }

    _stopHeartbeat() {
      if (this.heartbeatTimer) {
        clearInterval(this.heartbeatTimer);
        this.heartbeatTimer = null;
      }
    }

    // ========================================================================
    // Message Handling
    // ========================================================================

    _send(message) {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        this._log('Cannot send, not connected');
        return false;
      }

      this.ws.send(JSON.stringify({
        ...message,
        timestamp: message.timestamp || Date.now()
      }));
      return true;
    }

    _handleMessage(message) {
      this._log('Received:', message.type, message.channel);

      // Handle request responses
      if (message.requestId && this.pendingRequests.has(message.requestId)) {
        const { resolve, reject } = this.pendingRequests.get(message.requestId);
        this.pendingRequests.delete(message.requestId);

        if (message.type === 'error') {
          reject(new Error(message.payload?.message || 'Request failed'));
        } else {
          resolve(message);
        }
        return;
      }

      // Route by message type
      switch (message.type) {
        case 'pong':
          // Heartbeat response, nothing to do
          break;

        case 'subscribed':
        case 'unsubscribed':
          // Subscription confirmations handled by pending requests
          break;

        case 'entity:created':
        case 'entity:updated':
        case 'entity:deleted':
          this._handleEntityEvent(message);
          break;

        case 'presence:join':
        case 'presence:leave':
        case 'presence:sync':
          this._handlePresenceEvent(message);
          break;

        case 'error':
          this._log('Server error:', message.payload);
          this._emit('error', message.payload);
          break;

        default:
          // Custom message types
          this._emit(message.type, message);
      }
    }

    _handleEntityEvent(message) {
      const channel = message.channel;

      // Notify channel subscribers
      const callbacks = this.subscriptions.get(channel) || [];
      callbacks.forEach(callback => {
        try {
          callback(message);
        } catch (e) {
          this._log('Subscription callback error:', e);
        }
      });

      // Emit typed event
      this._emit(message.type, message);
    }

    _handlePresenceEvent(message) {
      const channel = message.channel;

      // Notify channel subscribers
      const callbacks = this.subscriptions.get(channel) || [];
      callbacks.forEach(callback => {
        try {
          callback(message);
        } catch (e) {
          this._log('Presence callback error:', e);
        }
      });

      // Emit typed event
      this._emit(message.type, message);
    }

    // ========================================================================
    // Channel Subscriptions
    // ========================================================================

    subscribe(channel, callback) {
      return new Promise((resolve, reject) => {
        const requestId = this._generateId();

        // Store callback
        if (!this.subscriptions.has(channel)) {
          this.subscriptions.set(channel, []);
        }
        this.subscriptions.get(channel).push(callback);

        // Track request
        this.pendingRequests.set(requestId, { resolve, reject });

        // Send subscribe message
        this._send({
          type: 'subscribe',
          channel,
          requestId
        });

        // Return unsubscribe function
        resolve(() => this.unsubscribe(channel, callback));
      });
    }

    unsubscribe(channel, callback) {
      const callbacks = this.subscriptions.get(channel);
      if (callbacks) {
        const index = callbacks.indexOf(callback);
        if (index > -1) {
          callbacks.splice(index, 1);
        }

        // If no more callbacks, unsubscribe from server
        if (callbacks.length === 0) {
          this.subscriptions.delete(channel);
          this._send({
            type: 'unsubscribe',
            channel
          });
        }
      }
    }

    // Convenience methods for entity subscriptions
    subscribeToEntity(entityName, callback) {
      return this.subscribe(`entity:${entityName}`, callback);
    }

    subscribeToRecord(entityName, id, callback) {
      return this.subscribe(`entity:${entityName}:${id}`, callback);
    }

    // ========================================================================
    // Presence
    // ========================================================================

    joinPresence(resource, metadata = {}) {
      return new Promise((resolve, reject) => {
        const requestId = this._generateId();

        this.pendingRequests.set(requestId, { resolve, reject });

        this._send({
          type: 'presence:join',
          requestId,
          payload: {
            resource,
            metadata
          }
        });
      });
    }

    leavePresence(resource) {
      this._send({
        type: 'presence:leave',
        payload: { resource }
      });
    }

    sendHeartbeat() {
      this._send({
        type: 'presence:heartbeat'
      });
    }

    // ========================================================================
    // Event Emitter
    // ========================================================================

    on(event, callback) {
      if (!this.listeners.has(event)) {
        this.listeners.set(event, []);
      }
      this.listeners.get(event).push(callback);

      return () => this.off(event, callback);
    }

    off(event, callback) {
      const callbacks = this.listeners.get(event);
      if (callbacks) {
        const index = callbacks.indexOf(callback);
        if (index > -1) {
          callbacks.splice(index, 1);
        }
      }
    }

    _emit(event, data) {
      const callbacks = this.listeners.get(event) || [];
      callbacks.forEach(callback => {
        try {
          callback(data);
        } catch (e) {
          this._log('Event listener error:', e);
        }
      });
    }

    // ========================================================================
    // Utilities
    // ========================================================================

    _generateId() {
      return 'req_' + Math.random().toString(36).substr(2, 9);
    }

    _log(...args) {
      if (this.options.debug) {
        console.log('[Realtime]', ...args);
      }
    }
  }

  // ==========================================================================
  // Optimistic Updates Manager
  // ==========================================================================

  class OptimisticManager {
    constructor(apiClient, realtimeClient) {
      this.apiClient = apiClient;
      this.realtimeClient = realtimeClient;
      this.pendingMutations = new Map();
    }

    async create(entityName, data, signal, options = {}) {
      // Generate temporary ID
      const tempId = `temp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      const optimisticData = { ...data, id: tempId, _optimistic: true };

      // Get current value
      const current = typeof signal === 'function' ? signal() : signal.value;

      // Update signal immediately (optimistic)
      if (Array.isArray(current)) {
        this._updateSignal(signal, [...current, optimisticData]);
      }

      // Track pending mutation
      this.pendingMutations.set(tempId, {
        type: 'create',
        entityName,
        optimisticData,
        originalData: current
      });

      try {
        // Send to server
        const result = await this.apiClient.create(entityName, data);

        // Replace optimistic entry with real data
        const updated = typeof signal === 'function' ? signal() : signal.value;
        if (Array.isArray(updated)) {
          this._updateSignal(signal, updated.map(item =>
            item.id === tempId ? result : item
          ));
        }

        this.pendingMutations.delete(tempId);
        return result;
      } catch (error) {
        // Rollback on error
        const updated = typeof signal === 'function' ? signal() : signal.value;
        if (Array.isArray(updated)) {
          this._updateSignal(signal, updated.filter(item => item.id !== tempId));
        }

        this.pendingMutations.delete(tempId);

        if (options.onError) {
          options.onError(error);
        } else {
          throw error;
        }
      }
    }

    async update(entityName, id, data, signal, options = {}) {
      // Get current value
      const current = typeof signal === 'function' ? signal() : signal.value;

      // Find original item
      let original = null;
      if (Array.isArray(current)) {
        original = current.find(item => item.id === id);
      } else if (current && current.id === id) {
        original = current;
      }

      if (!original) {
        return this.apiClient.update(entityName, id, data);
      }

      // Create optimistic data
      const optimisticData = { ...original, ...data, _optimistic: true };

      // Update signal immediately
      if (Array.isArray(current)) {
        this._updateSignal(signal, current.map(item =>
          item.id === id ? optimisticData : item
        ));
      } else {
        this._updateSignal(signal, optimisticData);
      }

      // Track pending mutation
      this.pendingMutations.set(id, {
        type: 'update',
        entityName,
        original,
        optimisticData
      });

      try {
        const result = await this.apiClient.update(entityName, id, data);

        // Replace with real data
        const updated = typeof signal === 'function' ? signal() : signal.value;
        if (Array.isArray(updated)) {
          this._updateSignal(signal, updated.map(item =>
            item.id === id ? result : item
          ));
        } else {
          this._updateSignal(signal, result);
        }

        this.pendingMutations.delete(id);
        return result;
      } catch (error) {
        // Rollback
        const updated = typeof signal === 'function' ? signal() : signal.value;
        if (Array.isArray(updated)) {
          this._updateSignal(signal, updated.map(item =>
            item.id === id ? original : item
          ));
        } else {
          this._updateSignal(signal, original);
        }

        this.pendingMutations.delete(id);

        if (options.onError) {
          options.onError(error);
        } else {
          throw error;
        }
      }
    }

    async delete(entityName, id, signal, options = {}) {
      // Get current value
      const current = typeof signal === 'function' ? signal() : signal.value;

      // Find original item
      let original = null;
      let originalIndex = -1;
      if (Array.isArray(current)) {
        originalIndex = current.findIndex(item => item.id === id);
        original = originalIndex >= 0 ? current[originalIndex] : null;
      }

      if (!original) {
        return this.apiClient.remove(entityName, id);
      }

      // Remove immediately (optimistic)
      this._updateSignal(signal, current.filter(item => item.id !== id));

      // Track pending mutation
      this.pendingMutations.set(id, {
        type: 'delete',
        entityName,
        original,
        originalIndex
      });

      try {
        await this.apiClient.remove(entityName, id);
        this.pendingMutations.delete(id);
      } catch (error) {
        // Rollback - reinsert at original position
        const updated = typeof signal === 'function' ? signal() : signal.value;
        if (Array.isArray(updated)) {
          const restored = [...updated];
          restored.splice(originalIndex, 0, original);
          this._updateSignal(signal, restored);
        }

        this.pendingMutations.delete(id);

        if (options.onError) {
          options.onError(error);
        } else {
          throw error;
        }
      }
    }

    _updateSignal(signal, value) {
      if (typeof signal === 'function' && signal.set) {
        // It's a DNR signal tuple [getter, setter]
        signal.set(value);
      } else if (signal && typeof signal.value !== 'undefined') {
        // It's a signal object with .value
        signal.value = value;
      } else if (Array.isArray(signal) && signal.length === 2) {
        // It's [getter, setter] tuple
        signal[1](value);
      }
    }

    hasPendingMutation(id) {
      return this.pendingMutations.has(id);
    }

    getPendingMutations() {
      return Array.from(this.pendingMutations.values());
    }
  }

  // ==========================================================================
  // Presence Manager (UI Helper)
  // ==========================================================================

  class PresenceManager {
    constructor(realtimeClient) {
      this.client = realtimeClient;
      this.resources = new Map(); // resource -> { users: Map, signal? }

      // Listen to presence events
      this.client.on('presence:join', (msg) => this._handleJoin(msg));
      this.client.on('presence:leave', (msg) => this._handleLeave(msg));
      this.client.on('presence:sync', (msg) => this._handleSync(msg));
    }

    async join(resource, metadata = {}) {
      // Initialize resource tracking
      if (!this.resources.has(resource)) {
        const users = new Map();
        let signal = null;

        // Create signal if DNR available
        if (global.DNR && global.DNR.createSignal) {
          const [getter, setter] = global.DNR.createSignal([]);
          signal = { get: getter, set: setter };
        }

        this.resources.set(resource, { users, signal });
      }

      await this.client.joinPresence(resource, metadata);
    }

    leave(resource) {
      this.client.leavePresence(resource);
      this.resources.delete(resource);
    }

    getUsers(resource) {
      const data = this.resources.get(resource);
      if (!data) return [];
      return Array.from(data.users.values());
    }

    getUsersSignal(resource) {
      const data = this.resources.get(resource);
      return data?.signal?.get || (() => []);
    }

    isUserPresent(resource, userId) {
      const data = this.resources.get(resource);
      return data?.users.has(userId) || false;
    }

    _handleJoin(message) {
      const resource = message.payload?.resource;
      const data = this.resources.get(resource);
      if (!data) return;

      const user = message.payload;
      data.users.set(user.userId, user);
      this._updateSignal(data);
    }

    _handleLeave(message) {
      const channel = message.channel || '';
      const resource = channel.replace('presence:', '');
      const data = this.resources.get(resource);
      if (!data) return;

      const userId = message.payload?.userId;
      data.users.delete(userId);
      this._updateSignal(data);
    }

    _handleSync(message) {
      const channel = message.channel || '';
      const resource = channel.replace('presence:', '');
      const data = this.resources.get(resource);
      if (!data) return;

      // Replace all users
      data.users.clear();
      (message.payload?.users || []).forEach(user => {
        data.users.set(user.userId, user);
      });
      this._updateSignal(data);
    }

    _updateSignal(data) {
      if (data.signal) {
        data.signal.set(Array.from(data.users.values()));
      }
    }
  }

  // ==========================================================================
  // Entity Sync (auto-update signals from realtime events)
  // ==========================================================================

  class EntitySync {
    constructor(realtimeClient) {
      this.client = realtimeClient;
      this.syncs = new Map(); // entityName -> { signal, unsubscribe }
    }

    sync(entityName, signal, options = {}) {
      // Unsubscribe existing sync
      this.unsync(entityName);

      const callback = (message) => {
        const current = typeof signal === 'function' ? signal() : signal.value;

        switch (message.type) {
          case 'entity:created': {
            const newItem = message.payload?.data;
            if (newItem && Array.isArray(current)) {
              // Don't add if it's from optimistic update (already in list)
              if (!current.some(item => item.id === newItem.id)) {
                this._updateSignal(signal, [...current, newItem]);
              }
            }
            break;
          }

          case 'entity:updated': {
            const updatedItem = message.payload?.data;
            const id = message.payload?.id;
            if (updatedItem && Array.isArray(current)) {
              this._updateSignal(signal, current.map(item =>
                item.id === id ? { ...item, ...updatedItem } : item
              ));
            } else if (updatedItem && current?.id === id) {
              this._updateSignal(signal, { ...current, ...updatedItem });
            }
            break;
          }

          case 'entity:deleted': {
            const id = message.payload?.id;
            if (Array.isArray(current)) {
              this._updateSignal(signal, current.filter(item => item.id !== id));
            }
            break;
          }
        }
      };

      // Subscribe to entity channel
      this.client.subscribeToEntity(entityName, callback).then(unsubscribe => {
        this.syncs.set(entityName, { signal, unsubscribe, callback });
      });
    }

    unsync(entityName) {
      const syncData = this.syncs.get(entityName);
      if (syncData) {
        syncData.unsubscribe();
        this.syncs.delete(entityName);
      }
    }

    unsyncAll() {
      this.syncs.forEach((_, entityName) => this.unsync(entityName));
    }

    _updateSignal(signal, value) {
      if (typeof signal === 'function' && signal.set) {
        signal.set(value);
      } else if (signal && typeof signal.value !== 'undefined') {
        signal.value = value;
      } else if (Array.isArray(signal) && signal.length === 2) {
        signal[1](value);
      }
    }
  }

  // ==========================================================================
  // Factory Function
  // ==========================================================================

  function createRealtimeClient(url, options = {}) {
    const client = new RealtimeClient(url, options);

    return {
      client,
      optimistic: new OptimisticManager(
        global.DNR?.api || { create: () => {}, update: () => {}, remove: () => {} },
        client
      ),
      presence: new PresenceManager(client),
      sync: new EntitySync(client),

      // Convenience methods
      connect: (token) => client.connect(token),
      disconnect: () => client.disconnect(),
      subscribe: (channel, callback) => client.subscribe(channel, callback),
      on: (event, callback) => client.on(event, callback)
    };
  }

  // ==========================================================================
  // Export
  // ==========================================================================

  const Realtime = {
    RealtimeClient,
    OptimisticManager,
    PresenceManager,
    EntitySync,
    createRealtimeClient
  };

  // Export to DNR namespace if available
  if (global.DNR) {
    global.DNR.Realtime = Realtime;
    global.DNR.createRealtimeClient = createRealtimeClient;
  }

  // Also export standalone
  global.DNRRealtime = Realtime;

})(typeof window !== 'undefined' ? window : global);
'''

# Lazy-loaded realtime JS
_REALTIME_JS_CACHED: str | None = None


def _get_realtime_js() -> str:
    """Get the realtime JS, loading from files if available."""
    global _REALTIME_JS_CACHED
    if _REALTIME_JS_CACHED is None:
        _REALTIME_JS_CACHED = _load_realtime_js()
    return _REALTIME_JS_CACHED


def get_realtime_client_js() -> str:
    """
    Get the realtime client JavaScript code.

    Loads from modular file in static/js/ if available,
    otherwise falls back to the inline version.

    Returns:
        JavaScript code as string
    """
    return _get_realtime_js()


# Backward compatibility - direct string access
# NOTE: This is the inline fallback for code that imports REALTIME_CLIENT_JS directly
REALTIME_CLIENT_JS = _REALTIME_CLIENT_JS_INLINE


def generate_realtime_init_js(websocket_url: str = "/ws", options: dict | None = None) -> str:
    """
    Generate JavaScript to initialize the realtime client.

    Args:
        websocket_url: WebSocket endpoint URL
        options: Client options

    Returns:
        JavaScript initialization code
    """
    options = options or {}
    options_js = ", ".join(f"{k}: {repr(v)}" for k, v in options.items())

    return f'''
// Initialize DNR Realtime Client
(function() {{
  'use strict';

  document.addEventListener('DOMContentLoaded', function() {{
    // Determine WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = protocol + '//' + window.location.host + '{websocket_url}';

    // Create realtime client
    const realtime = DNR.createRealtimeClient(wsUrl, {{
      debug: true,
      {options_js}
    }});

    // Connect (with auth token if available)
    const token = localStorage.getItem('dnr_auth_token');
    realtime.connect(token).then(() => {{
      console.log('[DNR] Realtime connected');
    }}).catch(err => {{
      console.warn('[DNR] Realtime connection failed:', err);
    }});

    // Export for debugging
    window.dnrRealtime = realtime;
  }});
}})();
'''
