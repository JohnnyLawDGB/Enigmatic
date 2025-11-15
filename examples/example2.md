
# Example 2: Script Hash Encoding

Message M is hashed:
H = sha256(M)

We take the low 20 bytes:
script_hash = H mod 2^160

Sender creates an output:
OP_HASH160 <script_hash> OP_EQUAL
