# Edge case: Unusual but valid whitespace
module corpus.whitespace
app whitespace_test "Whitespace Test"

entity Item "Item":
  id: uuid pk
  name:    str(200)    required
  count:int  optional


surface item_list   "Items":
  uses entity   Item
  mode:     list
  section    main:
    field name     "Name"
    field    count "Count"
