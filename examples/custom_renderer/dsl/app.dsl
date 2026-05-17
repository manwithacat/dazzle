# Custom renderer worked example.
#
# Minimal DSL: one entity, two surfaces. The `tag_cloud` surface uses
# `mode: custom` + `render: word_cloud` to dispatch through the
# project's hand-rolled renderer instead of the built-in fragment
# renderer. The `feedback_list` surface uses the default fragment
# renderer for comparison.

module custom_renderer.core

app custom_renderer "Custom Renderer Example"

# A pile of free-text feedback items — small enough to fit in
# the example, large enough to make the word-cloud meaningful.
entity Feedback "Feedback":
  intent: "Free-text user feedback aggregated into a word cloud"
  domain: example
  id: uuid pk
  body: text required
  sentiment: enum[positive,neutral,negative]=neutral
  created_at: datetime auto_add

# Standard list surface — uses the built-in fragment renderer.
# No `render:` clause = the default.
surface feedback_list "All Feedback":
  uses entity Feedback
  mode: list
  section main:
    field body "Feedback"
    field sentiment "Tone"
    field created_at "When"

# Custom surface — `render: word_cloud` dispatches through the
# handler registered in `app/render/word_cloud.py`. Because the
# renderer is project-side, the name has to be declared in
# `dazzle.toml`'s `[renderers] extra = […]` allowlist OR the
# linker rejects this surface at `dazzle validate` time.
surface tag_cloud "Feedback word cloud":
  uses entity Feedback
  mode: custom
  render: word_cloud
