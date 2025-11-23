# DAZZLE v0.2.0 Roadmap

**Status**: Planning
**Target Release**: Q1 2026
**Focus**: Testing, Quality, Production Readiness

> **📍 Navigation**: This document details v0.2.0 feature planning.
> For the master roadmap and version timeline, see **`/ROADMAP.md`** (single source of truth).

---

## Overview

Version 0.2.0 focuses on **testing infrastructure**, **code quality improvements**, and **production-readiness features** based on real-world feedback from Urban Canopy testing.

**Goals**:
- Add automated test generation for generated code
- Improve database handling (migrations vs sync)
- Add monitoring and health check capabilities
- Enhance security with best practices
- Improve developer experience

---

## Priority 1: Generated Tests (HIGH)

### Objective
Generate basic test structure and tests for CRUD operations

### express_micro Stack

**1. Test Structure Generation**:
```
tests/
  ├── setup.js              # Test configuration
  ├── models/
  │   ├── volunteer.test.js # Model tests
  │   └── tree.test.js
  └── routes/
      ├── volunteer.test.js # Route tests
      └── tree.test.js
```

**2. Model Test Template**:
```javascript
// tests/models/volunteer.test.js
const { Volunteer } = require('../models');

describe('Volunteer Model', () => {
  beforeEach(async () => {
    await Volunteer.sync({ force: true });
  });

  it('should create a volunteer', async () => {
    const volunteer = await Volunteer.create({
      name: 'Test User',
      skill_level: 'Beginner'
    });
    expect(volunteer.name).toBe('Test User');
  });

  it('should validate required fields', async () => {
    await expect(Volunteer.create({}))
      .rejects.toThrow();
  });
});
```

**3. Route Test Template**:
```javascript
// tests/routes/volunteer.test.js
const request = require('supertest');
const app = require('../server');

describe('Volunteer Routes', () => {
  it('GET / should list volunteers', async () => {
    const res = await request(app).get('/volunteer');
    expect(res.statusCode).toBe(200);
  });

  it('POST / should create volunteer', async () => {
    const res = await request(app)
      .post('/volunteer')
      .send({ name: 'Test', skill_level: 'Beginner' });
    expect(res.statusCode).toBe(302); // redirect
  });
});
```

**4. Dependencies to Add**:
```json
"devDependencies": {
  "jest": "^29.7.0",
  "supertest": "^6.3.3",
  "@types/jest": "^29.5.8"
}
```

**5. Scripts to Add**:
```json
"scripts": {
  "test": "jest",
  "test:watch": "jest --watch",
  "test:coverage": "jest --coverage"
}
```

**Implementation Estimate**: 2-3 days

---

## Priority 2: Database Migrations (HIGH)

### Objective
Replace `sync({force: true})` with proper migration system

### Current Problem
- `npm run init-db` destroys all data
- No migration history
- Dangerous in production

### Solution

**1. Add Sequelize CLI**:
```json
"devDependencies": {
  "sequelize-cli": "^6.6.2"
}
```

**2. Generate Sequelize Config**:
```javascript
// config/config.js
module.exports = {
  development: {
    dialect: 'sqlite',
    storage: './database.sqlite'
  },
  production: {
    use_env_variable: 'DATABASE_URL',
    dialect: 'postgres'
  }
};
```

**3. Generate Initial Migration**:
```javascript
// migrations/20250101000000-create-volunteer.js
module.exports = {
  async up(queryInterface, Sequelize) {
    await queryInterface.createTable('volunteers', {
      id: {
        type: Sequelize.UUID,
        defaultValue: Sequelize.UUIDV4,
        primaryKey: true
      },
      name: {
        type: Sequelize.STRING(200),
        allowNull: false
      },
      // ... other fields
    });
  },
  async down(queryInterface, Sequelize) {
    await queryInterface.dropTable('volunteers');
  }
};
```

**4. Update Scripts**:
```json
"scripts": {
  "migrate": "sequelize-cli db:migrate",
  "migrate:undo": "sequelize-cli db:migrate:undo",
  "migrate:status": "sequelize-cli db:migrate:status",
  "init-db": "sequelize-cli db:migrate" // NEW: use migrations
}
```

**5. Update README**:
- Document migration workflow
- Explain how to modify schema
- Add rollback instructions

**Implementation Estimate**: 3-4 days

---

## Priority 3: Health Check Endpoint (MEDIUM)

### Objective
Add `/health` endpoint for monitoring and deployment

### Implementation

**1. Health Check Route**:
```javascript
// Add to server.js
app.get('/health', async (req, res) => {
  const health = {
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    environment: process.env.NODE_ENV || 'development'
  };

  try {
    // Check database connection
    await db.sequelize.authenticate();
    health.database = 'connected';
  } catch (error) {
    health.status = 'unhealthy';
    health.database = 'disconnected';
    health.error = error.message;
    return res.status(503).json(health);
  }

  res.json(health);
});
```

**2. Detailed Health Check** (optional):
```javascript
app.get('/health/detailed', async (req, res) => {
  const health = {
    status: 'healthy',
    checks: {}
  };

  // Database check
  try {
    await db.sequelize.authenticate();
    health.checks.database = { status: 'up' };
  } catch (error) {
    health.checks.database = { status: 'down', error: error.message };
    health.status = 'degraded';
  }

  // Disk space check (optional)
  // Memory check (optional)

  res.json(health);
});
```

**Implementation Estimate**: 1 day

---

## Priority 4: Security Headers (MEDIUM)

### Objective
Add helmet for security best practices

### Implementation

**1. Add Dependency**:
```json
"dependencies": {
  "helmet": "^7.1.0"
}
```

**2. Add to Server**:
```javascript
const helmet = require('helmet');

app.use(helmet({
  contentSecurityPolicy: {
    directives: {
      defaultSrc: ["'self'"],
      styleSrc: ["'self'", "'unsafe-inline'"], // For inline styles
      scriptSrc: ["'self'"]
    }
  }
}));
```

**3. Document in README**:
- Explain what helmet does
- Show how to customize CSP
- Note about inline styles/scripts

**Implementation Estimate**: 1 day

---

## Priority 5: Pagination Support (MEDIUM)

### Objective
Add pagination to list routes for better performance

### Implementation

**1. Update List Routes**:
```javascript
// Before
router.get('/', async (req, res) => {
  const volunteers = await Volunteer.findAll({
    order: [['createdAt', 'DESC']]
  });
  res.render('volunteer/list', { title: 'Volunteers', volunteers });
});

// After
router.get('/', async (req, res) => {
  const page = parseInt(req.query.page) || 1;
  const limit = parseInt(req.query.limit) || 20;
  const offset = (page - 1) * limit;

  const { count, rows } = await Volunteer.findAndCountAll({
    limit,
    offset,
    order: [['createdAt', 'DESC']]
  });

  res.render('volunteer/list', {
    title: 'Volunteers',
    volunteers: rows,
    pagination: {
      page,
      limit,
      total: count,
      totalPages: Math.ceil(count / limit),
      hasNext: page < Math.ceil(count / limit),
      hasPrev: page > 1
    }
  });
});
```

**2. Update List Template**:
```html
<!-- views/volunteer/list.ejs -->
<div class="pagination">
  <% if (pagination.hasPrev) { %>
    <a href="?page=<%= pagination.page - 1 %>">Previous</a>
  <% } %>

  <span>Page <%= pagination.page %> of <%= pagination.totalPages %></span>

  <% if (pagination.hasNext) { %>
    <a href="?page=<%= pagination.page + 1 %>">Next</a>
  <% } %>
</div>
```

**3. Add Pagination CSS**:
```css
.pagination {
  display: flex;
  justify-content: center;
  gap: 1rem;
  margin: 2rem 0;
}
```

**Implementation Estimate**: 2 days

---

## Priority 6: Database Indexes (MEDIUM)

### Objective
Auto-generate indexes on foreign keys and commonly queried fields

### Implementation

**1. Add Indexes to Models**:
```javascript
// models/Tree.js
module.exports = (sequelize, DataTypes) => {
  const Tree = sequelize.define('Tree', {
    // ... fields
  }, {
    indexes: [
      { fields: ['steward'] },        // Foreign key
      { fields: ['species'] },         // Commonly queried
      { fields: ['created_at'] },      // For ordering
      {
        fields: ['location_lat', 'location_lng'],  // Composite for geo queries
        name: 'idx_location'
      }
    ]
  });
  return Tree;
};
```

**2. Detection Logic**:
```python
# In express_micro.py
def _get_model_indexes(entity):
    indexes = []

    # Add index on foreign keys
    for field in entity.fields:
        if field.type.ref_entity:
            indexes.append(f"{{ fields: ['{field.name}'] }}")

    # Add index on created_at for ordering
    if any(f.name == 'created_at' for f in entity.fields):
        indexes.append("{ fields: ['created_at'] }")

    return indexes
```

**Implementation Estimate**: 2 days

---

## Priority 7: Logging Framework (MEDIUM)

### Objective
Add structured logging with winston or pino

### Implementation

**1. Add Dependency**:
```json
"dependencies": {
  "winston": "^3.11.0"
}
```

**2. Create Logger**:
```javascript
// utils/logger.js
const winston = require('winston');

const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.File({ filename: 'error.log', level: 'error' }),
    new winston.transports.File({ filename: 'combined.log' }),
    new winston.transports.Console({
      format: winston.format.simple()
    })
  ]
});

module.exports = logger;
```

**3. Use in Routes**:
```javascript
const logger = require('../utils/logger');

router.get('/', async (req, res) => {
  logger.info('Fetching volunteers list');
  try {
    const volunteers = await Volunteer.findAll();
    res.render('volunteer/list', { volunteers });
  } catch (error) {
    logger.error('Error fetching volunteers', { error: error.message, stack: error.stack });
    res.status(500).send('Error loading data');
  }
});
```

**Implementation Estimate**: 2 days

---

## Lower Priority Features

### P8: Flash Messages (LOW)
- Session-based success/error messages
- Requires express-session
- Estimate: 1-2 days

### P9: CORS Support (LOW)
- Optional CORS configuration
- Commented out by default
- Estimate: 0.5 day

### P10: Input Sanitization (LOW)
- Add .trim(), .escape() to validators
- XSS prevention
- Estimate: 1 day

### P11: Docker Support (LOW)
- Generate Dockerfile and docker-compose.yml
- Estimate: 2 days

### P12: Seed Data (LOW)
- Generate seed scripts
- Sample data for testing
- Estimate: 2 days

---

## Implementation Plan

### Phase 1: Testing (Week 1-2)
- ✅ Generated tests for models and routes
- ✅ Jest configuration
- ✅ Test documentation

### Phase 2: Database (Week 3)
- ✅ Migration system
- ✅ Sequelize CLI integration
- ✅ Migration generation
- ✅ Documentation

### Phase 3: Production Features (Week 4)
- ✅ Health check endpoint
- ✅ Security headers (helmet)
- ✅ Database indexes
- ✅ Logging framework

### Phase 4: Performance (Week 5)
- ✅ Pagination support
- ✅ Optimize queries
- ✅ Add caching hints

### Phase 5: Polish (Week 6)
- Flash messages
- Input sanitization
- Final documentation
- Release preparation

---

## Success Criteria

**v0.2.0 is ready when**:
1. ✅ All generated apps include tests
2. ✅ Database migrations work (no more force sync)
3. ✅ Health check endpoint responds
4. ✅ Security headers applied
5. ✅ Pagination works on list views
6. ✅ Database indexes auto-generated
7. ✅ Logging framework integrated
8. ✅ All features documented
9. ✅ Urban Canopy rebuilt and verified
10. ✅ CHANGELOG updated

---

## Testing Plan

### Unit Tests
- Test migration generation
- Test index detection logic
- Test pagination helper functions

### Integration Tests
- Build Urban Canopy with v0.2.0
- Run generated tests
- Verify migrations work
- Test health check endpoint
- Verify pagination with large datasets

### Performance Tests
- List view with 10,000 records (pagination)
- Database query performance (indexes)

---

## Documentation Updates

### New Docs Needed
- Migration workflow guide
- Testing guide for generated apps
- Health check monitoring guide
- Deployment best practices (updated)

### Updated Docs
- README.md (new features)
- Stack capabilities matrix
- User guide (testing section)

---

## Breaking Changes

**None expected** - all changes are additive or improvements

**Migration Path**:
- Existing v0.1.x apps continue to work
- New features optional (can be adopted gradually)
- Migration to new init-db is opt-in

---

## Dependencies Added

```json
// express_micro stack
"dependencies": {
  "helmet": "^7.1.0",
  "winston": "^3.11.0"
},
"devDependencies": {
  "jest": "^29.7.0",
  "supertest": "^6.3.3",
  "@types/jest": "^29.5.8",
  "sequelize-cli": "^6.6.2"
}
```

---

## Estimated Timeline

**Total Development**: 5-6 weeks
**Testing & QA**: 1 week
**Documentation**: 1 week
**Total**: 7-8 weeks

---

## Resources Needed

- [ ] Testing framework expertise
- [ ] Sequelize migrations knowledge
- [ ] Security best practices review
- [ ] Performance testing tools

---

## Risk Mitigation

**Risk**: Migration system too complex
**Mitigation**: Keep it simple, generate basic migrations only

**Risk**: Breaking existing apps
**Mitigation**: Extensive testing, opt-in features

**Risk**: Performance overhead
**Mitigation**: Benchmark before/after, optimize critical paths

---

## Future (v0.3.0+)

Items deferred to later versions:
- Advanced validation rules in DSL
- Computed fields
- Hooks/triggers in DSL
- Real-time features (WebSockets)
- Authentication generation
- Authorization (RBAC)

---

**Status**: Ready for Development
**Next Steps**:
1. Create feature branches for each priority
2. Start with P1 (Generated Tests)
3. Regular check-ins after each priority complete
