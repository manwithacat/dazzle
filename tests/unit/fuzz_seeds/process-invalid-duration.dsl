module test.core
app a "A"

process p "P":
  trigger:
    when: entity Order status -> confirmed
  steps:
    - step gen:
        service: gen
        timeout: 30x
