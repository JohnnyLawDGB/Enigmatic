# 02 — Encoding Primitives

This section defines the basic building blocks that Enigmatic uses to carry
information on DigiByte.

## 2.1 Value Plane

Reserved / example header values:

- `7.00` — segment marker  
- `11.11` — round start / header  
- `21.21` — broadcast or higher-level frame marker  
- `64.00` — power-of-two boundary  

Values are always exact to 1e-8 DGB and chosen to remain plausible to external
observers.

## 2.2 Fee Plane

Fees are used as an orthogonal signal:

- Example ranges:  
  - `0.21` DGB ± ε  
  - `2.10` DGB ± ε  
  - `21.00` DGB ± ε  

Where ε is small noise to avoid obvious fingerprinting.

## 2.3 Cardinality Plane

Input and output counts form a low-bandwidth but robust channel:

- `m = |IN_t|`  
- `n = |OUT_t|`  

Patterns like `m = 21, n = 21` or prime `m, n` can encode additional bits.

## 2.4 Optional OP_RETURN Plane

OP_RETURN is used sparingly for:

- Version tagging  
- Hash commitments  
- Protocol negotiation  

## 2.5 Bit-Packets

Bit-packets are small DGB values such as `0.0100xxxx` where the 8 decimal
digits after the decimal point carry a code point.

Example:

- `0.01001101` → `01001101₂` → symbol in an application dictionary.

The protocol does not mandate a single mapping; instead, it defines how
dictionaries are negotiated and applied.
