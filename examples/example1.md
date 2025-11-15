
# Example 1: Value-Based Encoding

Suppose a sender wishes to encode the number 314.

They choose `k = 21`.

Compute:
- `E_v = 314 mod 21 = 20`
- `E_o = floor(314 / 21) = 14`

Thus they create:
- Output index = 14
- Value = 20.000000 DGB (or 20 sats depending on context)

The receiver recombines:
M = E_v + k * E_o = 20 + 21*14 = 314
