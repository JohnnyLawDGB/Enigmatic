
# Appendix A: Mathematical Foundations of UTXO Encoding Theory

## A.1 UTXO State Space

Let a UTXO be defined as a tuple:

\[
U = (v, a, s)
\]

Where:  
- \( v \in \mathbb{R}^+ \) is the value (DGB)  
- \( a \in \mathcal{A} \) is the address space (set of valid DGB addresses)  
- \( s \in \mathcal{S} \) is the scriptPubKey space  

The global UTXO set at block height \( h \) is:

\[
\mathcal{U}_h = \{ U_1, U_2, \dots, U_n \}
\]

## A.2 Message Representation

A message \( M \) is encoded as:

\[
M \rightarrow (E_v, E_o, E_s)
\]

Where each component is mapped onto:

- **Value field (v):**  
  \[
  E_v = f_v(M) = M \bmod k
  \]
  for some modulus \( k \)

- **Output index (n):**  
  \[
  E_o = f_o(M) = \lfloor M / k \rfloor
  \]

- **Script pattern:**  
  \[
  E_s = f_s(M) = H(M) \bmod 2^{160}
  \]

This allows multiple orthogonal encoding channels.

## A.3 Multi-Layer Encoding

Given a set of orthogonal channels:

\[
C = \{c_1, c_2, \dots, c_m\}
\]

The total message capacity for a transaction \( T \) is:

\[
\mathcal{C}(T) = \sum_{i=1}^{m} \mathcal{C}(c_i)
\]

Where capacity for UTXO-value channel is:

\[
\mathcal{C}(c_v) = \log_2(v_{\max}) - \log_2(\epsilon)
\]

## A.4 Time-Chain Embedding

If you encode across block heights:

\[
M_i = f_h(h_i)
\]

Where:

\[
h_i = \text{block height of tx } i
\]

Then the message sequence is recoverable by:

\[
M = \sum_i M_i \cdot b^i
\]

for some base \( b \).

## A.5 Hash-Derived Noise Layer

Given:

\[
H = \text{sha256(txid)}
\]

A noise-resistant message can be:

\[
m = H \oplus K
\]

Where \( K \) is a shared key.

