module test.core
app a "A"

notification n "N":
  on: Invoice created
  channels: [not_a_channel]
  message: "hi"
