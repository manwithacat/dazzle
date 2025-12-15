# Fuzz seed: Basic structure for mutation testing
module corpus.fuzz
app fuzz_app "Fuzz"

entity E "E":
  id: uuid pk
  s: str(10) required
  n: int optional

surface s1 "S":
  uses entity E
  mode: list
  section m:
    field s "S"
