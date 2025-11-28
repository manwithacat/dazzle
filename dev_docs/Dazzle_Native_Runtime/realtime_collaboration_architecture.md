# Real-time & Collaboration Architecture

## Phase 2 Week 13-14: DNR Real-time Features

**Status**: In Progress
**Goal**: Add real-time capabilities for multi-user collaboration

---

## Overview

This document describes the architecture for adding real-time features to DNR:
- WebSocket support for bidirectional communication
- Live updates when other users modify data
- Optimistic UI updates for responsive user experience
- Presence indicators showing who's online

---

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        Browser Client                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Optimistic  │  │  Presence   │  │   Realtime Signals      │ │
│  │   Manager   │  │   Client    │  │ (reactive data binding) │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│         │               │                      │                │
│         └───────────────┼──────────────────────┘                │
│                         │                                        │
│              ┌──────────▼──────────┐                            │
│              │   RealtimeClient    │                            │
│              │   (WebSocket)       │                            │
│              └──────────┬──────────┘                            │
└─────────────────────────┼───────────────────────────────────────┘
                          │ WebSocket
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                     FastAPI Backend                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  WebSocketManager                          │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │  │
│  │  │ Connection │  │ Channel    │  │ Presence           │  │  │
│  │  │ Registry   │  │ Subscriptions│  │ Tracker           │  │  │
│  │  └────────────┘  └────────────┘  └────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                         │                                        │
│              ┌──────────▼──────────┐                            │
│              │    EventBus         │                            │
│              │ (Entity Changes)    │                            │
│              └──────────┬──────────┘                            │
│                         │                                        │
│              ┌──────────▼──────────┐                            │
│              │    Repository       │                            │
│              │  (CRUD + Events)    │                            │
│              └─────────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

### Components

#### Backend Components

1. **WebSocketManager** (`websocket_manager.py`)
   - Manages WebSocket connections
   - Routes messages to handlers
   - Broadcasts events to subscribers
   - Handles connection lifecycle

2. **ChannelManager** (`channel_manager.py`)
   - Pub/sub channels for entity changes
   - Supports per-entity and per-record subscriptions
   - Filters broadcasts by user permissions

3. **PresenceTracker** (`presence_tracker.py`)
   - Tracks which users are viewing which resources
   - Heartbeat-based online status
   - Broadcasts presence changes

4. **EventBus** (`event_bus.py`)
   - Decoupled event publishing from repositories
   - Hooks into CRUD operations
   - Triggers WebSocket broadcasts

#### Frontend Components

1. **RealtimeClient** (`realtime.js`)
   - WebSocket connection management
   - Automatic reconnection
   - Message serialization

2. **ChannelSubscriber** (`channels.js`)
   - Subscribe to entity/record changes
   - Update signals when data changes
   - Cleanup on unsubscribe

3. **PresenceManager** (`presence.js`)
   - Track and display who's online
   - Show who's viewing same resource
   - Heartbeat for activity

4. **OptimisticManager** (`optimistic.js`)
   - Immediate UI updates before server confirmation
   - Rollback on server error
   - Conflict resolution

---

## Message Protocol

### WebSocket Message Format

```typescript
interface RealtimeMessage {
  type: MessageType;
  channel?: string;
  payload: any;
  requestId?: string;  // For request-response correlation
  timestamp: number;
}

type MessageType =
  // Channel operations
  | 'subscribe'
  | 'unsubscribe'
  | 'subscribed'
  | 'unsubscribed'
  // Data events
  | 'entity:created'
  | 'entity:updated'
  | 'entity:deleted'
  // Presence
  | 'presence:join'
  | 'presence:leave'
  | 'presence:sync'
  | 'presence:heartbeat'
  // System
  | 'ping'
  | 'pong'
  | 'error';
```

### Channel Naming

```
entity:{entity_name}           - All changes to entity type
entity:{entity_name}:{id}      - Specific record changes
presence:{resource}            - Who's viewing resource
user:{user_id}                 - Private channel for user
```

### Example Messages

**Subscribe to entity changes:**
```json
{
  "type": "subscribe",
  "channel": "entity:Task",
  "requestId": "req_123",
  "timestamp": 1701234567890
}
```

**Entity created event:**
```json
{
  "type": "entity:created",
  "channel": "entity:Task",
  "payload": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "title": "New task",
    "status": "open",
    "created_at": "2024-11-28T10:00:00Z"
  },
  "timestamp": 1701234567890
}
```

**Presence update:**
```json
{
  "type": "presence:sync",
  "channel": "presence:workspace/tasks",
  "payload": {
    "users": [
      {"id": "user1", "name": "Alice", "lastSeen": 1701234560000},
      {"id": "user2", "name": "Bob", "lastSeen": 1701234567000}
    ]
  },
  "timestamp": 1701234567890
}
```

---

## Implementation Details

### Backend: WebSocketManager

```python
@dataclass
class Connection:
    """A WebSocket connection."""
    id: str
    websocket: WebSocket
    user_id: str | None
    subscriptions: set[str]
    connected_at: datetime
    last_heartbeat: datetime

class WebSocketManager:
    """Manages WebSocket connections and message routing."""

    def __init__(self):
        self._connections: dict[str, Connection] = {}
        self._channels: dict[str, set[str]] = {}  # channel -> connection_ids
        self._presence: PresenceTracker = PresenceTracker()

    async def connect(self, websocket: WebSocket, user_id: str | None = None) -> str:
        """Accept a new WebSocket connection."""

    async def disconnect(self, connection_id: str) -> None:
        """Handle connection disconnect."""

    async def subscribe(self, connection_id: str, channel: str) -> None:
        """Subscribe a connection to a channel."""

    async def unsubscribe(self, connection_id: str, channel: str) -> None:
        """Unsubscribe a connection from a channel."""

    async def broadcast(self, channel: str, message: dict) -> None:
        """Broadcast a message to all subscribers of a channel."""

    async def send_to_user(self, user_id: str, message: dict) -> None:
        """Send a message to all connections for a user."""
```

### Backend: EventBus Integration

```python
class EntityEventBus:
    """Publishes entity change events."""

    def __init__(self, ws_manager: WebSocketManager):
        self._ws_manager = ws_manager

    async def emit_created(self, entity_name: str, data: dict) -> None:
        """Emit entity created event."""
        await self._ws_manager.broadcast(
            f"entity:{entity_name}",
            {
                "type": "entity:created",
                "channel": f"entity:{entity_name}",
                "payload": data,
                "timestamp": time.time() * 1000,
            }
        )

    async def emit_updated(self, entity_name: str, id: str, data: dict) -> None:
        """Emit entity updated event."""
        # Broadcast to entity channel and specific record channel

    async def emit_deleted(self, entity_name: str, id: str) -> None:
        """Emit entity deleted event."""
```

### Backend: Presence Tracking

```python
@dataclass
class PresenceEntry:
    """A presence entry for a user in a resource."""
    user_id: str
    user_name: str | None
    resource: str
    last_seen: datetime
    metadata: dict[str, Any]

class PresenceTracker:
    """Tracks user presence across resources."""

    def __init__(self, timeout_seconds: int = 30):
        self._entries: dict[str, dict[str, PresenceEntry]] = {}
        self._timeout = timeout_seconds

    def join(self, resource: str, user_id: str, name: str | None = None) -> None:
        """User joined a resource."""

    def leave(self, resource: str, user_id: str) -> None:
        """User left a resource."""

    def heartbeat(self, resource: str, user_id: str) -> None:
        """Update user's last seen time."""

    def get_present(self, resource: str) -> list[PresenceEntry]:
        """Get all users present at a resource."""

    def cleanup_stale(self) -> list[tuple[str, str]]:
        """Remove stale entries, returns (resource, user_id) pairs."""
```

### Frontend: RealtimeClient

```javascript
class RealtimeClient {
  constructor(url, options = {}) {
    this.url = url;
    this.options = {
      reconnectInterval: 1000,
      maxReconnectAttempts: 10,
      heartbeatInterval: 25000,
      ...options
    };
    this.ws = null;
    this.connected = signal(false);
    this.subscriptions = new Map();
    this.pendingRequests = new Map();
    this.reconnectAttempts = 0;
  }

  connect() {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => this._onOpen();
    this.ws.onclose = () => this._onClose();
    this.ws.onmessage = (e) => this._onMessage(JSON.parse(e.data));
    this.ws.onerror = (e) => this._onError(e);
  }

  subscribe(channel, callback) {
    const id = generateId();
    this.subscriptions.set(id, { channel, callback });
    this._send({ type: 'subscribe', channel, requestId: id });
    return () => this.unsubscribe(id);
  }

  unsubscribe(id) {
    const sub = this.subscriptions.get(id);
    if (sub) {
      this._send({ type: 'unsubscribe', channel: sub.channel });
      this.subscriptions.delete(id);
    }
  }

  _onMessage(message) {
    // Route to appropriate handler
    if (message.type.startsWith('entity:')) {
      this._handleEntityEvent(message);
    } else if (message.type.startsWith('presence:')) {
      this._handlePresenceEvent(message);
    }
  }
}
```

### Frontend: Optimistic Updates

```javascript
class OptimisticManager {
  constructor(apiClient, realtimeClient) {
    this.apiClient = apiClient;
    this.realtimeClient = realtimeClient;
    this.pendingMutations = new Map();
  }

  async create(entityName, data, signal) {
    // Generate temporary ID
    const tempId = `temp_${Date.now()}`;
    const optimisticData = { ...data, id: tempId, _optimistic: true };

    // Update signal immediately
    const current = signal.value;
    signal.value = [...current, optimisticData];

    try {
      // Send to server
      const result = await this.apiClient.create(entityName, data);

      // Replace optimistic entry with real data
      signal.value = signal.value.map(item =>
        item.id === tempId ? result : item
      );

      return result;
    } catch (error) {
      // Rollback on error
      signal.value = signal.value.filter(item => item.id !== tempId);
      throw error;
    }
  }

  async update(entityName, id, data, signal) {
    // Store original for rollback
    const original = signal.value.find(item => item.id === id);
    const optimisticData = { ...original, ...data, _optimistic: true };

    // Update signal immediately
    signal.value = signal.value.map(item =>
      item.id === id ? optimisticData : item
    );

    try {
      const result = await this.apiClient.update(entityName, id, data);
      signal.value = signal.value.map(item =>
        item.id === id ? result : item
      );
      return result;
    } catch (error) {
      // Rollback
      signal.value = signal.value.map(item =>
        item.id === id ? original : item
      );
      throw error;
    }
  }

  async delete(entityName, id, signal) {
    const original = signal.value.find(item => item.id === id);

    // Remove immediately
    signal.value = signal.value.filter(item => item.id !== id);

    try {
      await this.apiClient.delete(entityName, id);
    } catch (error) {
      // Rollback
      signal.value = [...signal.value, original];
      throw error;
    }
  }
}
```

---

## FastAPI WebSocket Integration

### WebSocket Endpoint

```python
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str | None = Query(None),
):
    # Authenticate if token provided
    user_id = None
    if token:
        user = await auth_store.validate_session(token)
        user_id = user.id if user else None

    # Accept connection
    connection_id = await ws_manager.connect(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_json()
            await ws_manager.handle_message(connection_id, data)
    except WebSocketDisconnect:
        await ws_manager.disconnect(connection_id)
```

### Repository Hook

```python
class RealtimeRepository(SQLiteRepository[T]):
    """Repository that emits events on CRUD operations."""

    def __init__(self, *args, event_bus: EntityEventBus, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_bus = event_bus

    async def create(self, data: dict) -> T:
        result = await super().create(data)
        await self._event_bus.emit_created(
            self.entity_name,
            result.model_dump()
        )
        return result

    async def update(self, id: UUID, data: dict) -> T | None:
        result = await super().update(id, data)
        if result:
            await self._event_bus.emit_updated(
                self.entity_name,
                str(id),
                result.model_dump()
            )
        return result

    async def delete(self, id: UUID) -> bool:
        success = await super().delete(id)
        if success:
            await self._event_bus.emit_deleted(self.entity_name, str(id))
        return success
```

---

## Security Considerations

### Authentication
- WebSocket connections can include auth token as query param
- Token validated on connect
- Subscriptions filtered by user permissions

### Authorization
- Channel subscriptions respect access control policies
- User can only subscribe to channels they have access to
- Presence only shows users with shared access

### Rate Limiting
- Limit subscriptions per connection (default: 50)
- Limit broadcast rate per channel
- Disconnect on abuse

---

## Testing Strategy

### Unit Tests
- WebSocketManager connection lifecycle
- Channel subscription/unsubscription
- Presence tracking accuracy
- Message routing

### Integration Tests
- Full WebSocket flow with FastAPI
- Repository events trigger broadcasts
- Multiple clients receive updates

### E2E Tests
- Browser connects to WebSocket
- Real-time updates appear in UI
- Presence shows correctly

---

## File Structure

```
src/dazzle_dnr_back/runtime/
├── websocket_manager.py      # WebSocket connection manager
├── channel_manager.py        # Pub/sub channels
├── presence_tracker.py       # Presence tracking
├── event_bus.py              # Entity change events
├── realtime_routes.py        # WebSocket endpoint

src/dazzle_dnr_ui/runtime/
├── js_generator.py           # (extended with realtime)
│
└── static/
    ├── realtime.js           # WebSocket client
    ├── channels.js           # Channel subscriptions
    ├── presence.js           # Presence UI
    └── optimistic.js         # Optimistic updates

tests/
├── test_websocket_manager.py
├── test_channels.py
├── test_presence.py
├── test_event_bus.py
└── test_realtime_integration.py
```

---

## Success Criteria

- [ ] WebSocket connection established from browser
- [ ] Entity changes broadcast to subscribers
- [ ] Multiple users see real-time updates
- [ ] Presence shows who's viewing
- [ ] Optimistic updates provide instant feedback
- [ ] Reconnection handles network issues
- [ ] Tests cover all components

---

## Implementation Order

1. **WebSocket Manager** - Core connection handling
2. **Event Bus** - Repository integration
3. **Channel Manager** - Pub/sub system
4. **Presence Tracker** - User presence
5. **Frontend Client** - Browser WebSocket
6. **Optimistic Updates** - UI responsiveness
7. **Integration** - Wire everything together
8. **Tests** - Comprehensive coverage
