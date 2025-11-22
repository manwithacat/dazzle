module support.auth

# This module provides authentication entities
# Used by support.core module

entity AuthToken "Authentication Token":
  id: uuid pk
  user_id: uuid required
  token: str(64) unique required
  expires_at: datetime required
  created_at: datetime auto_add

  index user_id
  index token
