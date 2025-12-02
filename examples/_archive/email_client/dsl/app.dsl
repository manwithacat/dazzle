# DAZZLE Email Client - MONITOR_WALL Archetype Example
# Demonstrates multiple moderate signals in a dashboard layout

module email_client.core

app email_client "Email Client"

# Email message entity
entity Message "Message":
  id: uuid pk
  subject: str(200) required
  sender: str(200) required
  recipient: str(200) required
  body: text required
  status: enum[unread,read,archived]=unread
  priority: enum[low,normal,high]=normal
  received_at: datetime auto_add
  read_at: datetime optional

# Workspace with multiple signals (3-5) - triggers MONITOR_WALL archetype
# Multiple moderate-weight signals create balanced dashboard
workspace inbox "Email Inbox":
  purpose: "Monitor emails across multiple views"

  # Unread count KPI
  unread_stats:
    source: Message
    aggregate:
      total_unread: count(Message WHERE status = 'unread')
      high_priority: count(Message WHERE priority = 'high')

  # Recent unread messages
  recent_unread:
    source: Message
    limit: 10

  # High priority messages
  priority_messages:
    source: Message
    limit: 5

  # All messages table
  all_messages:
    source: Message
