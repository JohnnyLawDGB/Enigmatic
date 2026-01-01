# Enigmatic — DigiByte Layer-0 Communication Protocol

**Enigmatic** is a Layer-0 steganographic communication protocol that encodes messages in DigiByte's native UTXO patterns. Instead of adding new opcodes or consensus rules, it uses the existing transaction structure—amounts, fees, input/output counts, topology, and timing—as a multi-dimensional message channel. Each transaction expresses a **state vector** that peers can interpret without on-chain metadata.

Named after the WWII Enigma cipher machine, the protocol brings structured cryptographic signaling to the blockchain era, honoring the codebreakers of Bletchley Park while pioneering modern steganography on a permissionless ledger.

---

## 🚀 Quick Start (30 seconds)

**The easiest way to start:**

```bash
git clone https://github.com/JohnnyLawDGB/Enigmatic.git
cd Enigmatic
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Launch the console (handles RPC credentials for you)
./console
```

The `./console` launcher will:
1. Prompt for your DigiByte RPC credentials (one-time setup)
2. Optionally save them to `~/.enigmatic.yaml`
3. Display the beautiful WWII Enigma-themed splash screen
4. Launch the interactive menu

**First time?** See [`CONSOLE_LAUNCHER.md`](CONSOLE_LAUNCHER.md) for details.

---

## ✨ What Can You Do?

**Interactive Console** (Menu-driven, beginner-friendly):
- **[1-5]** Send steganographic patterns (symbols, sequences, chains)
- **[6-7]** Decode and watch on-chain activity
- **[8]** Prime ladder experiments
- **[9]** Taproot inscription wizard (with proper BIP341 commitments!)
- **[10]** Generate/decode unspendable vanity addresses

**Command-Line Interface** (Power users):
- Plan/send dialect-driven symbols: `enigmatic-dgb plan-symbol`, `send-symbol`
- Create Taproot inscriptions: `enigmatic-dgb ord-wizard`, `ord-inscribe`
- DTSP fee-plane messaging: `enigmatic-dgb dtsp-encode`, `dtsp-send`
- Generate unspendable addresses: `enigmatic-dgb unspendable DCx "MESSAGE"`
- Watch and decode: `enigmatic-dgb watch`, `ord-decode`

---

## 🎯 Core Concepts

### State Planes

Enigmatic encodes meaning across 6 dimensions of every transaction:

| Plane | What It Encodes | Example |
|-------|----------------|---------|
| **Value** | Amount anchors, headers | `21.21` DGB beacon |
| **Fee** | Timing, jitter bands | `0.21` DGB cadence |
| **Cardinality** | Input/output counts | `21 in / 21 out` symmetry |
| **Topology** | Output graph patterns | Fan-out trees, rings |
| **Block Placement** | Height deltas, repetition | `Δheight = 3` heartbeat |
| **Auxiliary** | Optional hints | OP_RETURN metadata |

### Dialects

A **dialect** maps human-readable **symbols** (like `HEARTBEAT` or `GENESIS`) to specific state vector patterns. Multi-transaction symbols become **frames** in a sequence. This keeps recurring intents consistent and decodable.

**Example:** The `dialect-showcase.yaml` includes symbols like:
- `genesis_bitcoin_2009` - Tribute to Bitcoin's genesis block
- `triptych_21_21_84` - DigiByte's sacred numbers
- `digishield_pulse` - References DigiShield difficulty adjustment
- `hello_enigmatic` - Simple greeting pattern

---

## 📚 Quick Examples

### 1. Send a Simple Pattern (Console)
```bash
./console
# Select [1] Quickstart
# Follow prompts to send value/fee patterns
```

### 2. Create a Taproot Inscription (Console)
```bash
./console
# Select [9] Taproot inscription wizard
# Choose payload type (text, JSON, hex)
# Review fees and broadcast
```

### 3. Generate an Unspendable Vanity Address (CLI)
```bash
enigmatic-dgb unspendable DCx "HAPPY2026"
# Output: DCxHAPPY2c26zzzzzzzzzzzzzzzzWnppyp
```

### 4. Send a Dialect Symbol (CLI)
```bash
enigmatic-dgb send-symbol \
  --dialect-path examples/dialect-heartbeat.yaml \
  --symbol HEARTBEAT \
  --to-address dgb1q... \
  --dry-run  # Review first!
```

### 5. Watch for On-Chain Activity (CLI)
```bash
enigmatic-dgb watch \
  --address dgb1q... \
  --start-height 22700000 \
  --limit 100
```

---

## 📖 Documentation

**New Users:**
- 🎮 Start with the **interactive console**: `./console`
- 📘 Read the [Simple Usage Guide](docs/simple_usage.md) for CLI basics
- 🧪 Try the [Taproot Inscription Lab](docs/taproot_inscription_lab.md) for step-by-step inscriptions

**Developers:**
- 🏗️ [Architecture Overview](docs/ARCHITECTURE.md) - Module design and code structure
- 🛠️ [Tooling Guide](docs/TOOLING.md) - Complete CLI command reference
- 📜 [Protocol Specifications](specs/) - Formal encoding/decoding rules

**Reference:**
- 📄 [Whitepaper](docs/whitepaper.md) - Full protocol narrative
- 🗺️ [Roadmap](docs/expansion-roadmap.md) - Future development priorities
- 🔒 [Security Model](specs/06-security-model.md) - Threat assumptions and deniability

---

## 🗂️ Repository Structure

```
Enigmatic/
├── enigmatic_dgb/       # Python implementation
│   ├── cli.py          # Command-line interface
│   ├── console.py      # Interactive menu system
│   ├── encoder.py      # State vector encoding
│   ├── decoder.py      # Message decoding
│   ├── planner.py      # UTXO selection & planning
│   ├── ordinals/       # Taproot inscription tools
│   └── ...
├── specs/              # Protocol specifications
├── docs/               # Documentation and guides
├── examples/           # Sample dialects and walkthroughs
├── tests/              # Pytest test suite
└── console             # Launcher script ⭐
```

---

## 🎨 Features Highlight

### Beautiful ASCII Splash Screen
The console greets you with a WWII Enigma machine tribute:
```
╔═══════════════════════════════════════════════════════════════════════════╗
║   ███████╗███╗   ██╗██╗ ██████╗ ███╗   ███╗ █████╗ ████████╗██╗ ██████╗ ║
║   [●] [●] [●]  Rotor Assembly: UTXO Pattern Encoding  [●] [●] [●]         ║
║   Q  W  E  R  T  Y  U  I  O  P     Plugboard: Address Mapping             ║
║   "In memory of Alan Turing and the codebreakers of Bletchley Park"       ║
║    Modern steganography meets WWII cryptographic heritage 1939-2026       ║
╚═══════════════════════════════════════════════════════════════════════════╝
```

### Proper BIP341 Taproot Inscriptions
Recent improvements ensure Taproot inscriptions **actually work**:
- ✅ Full BIP341 implementation with tagged hashing
- ✅ Proper key tweaking and merkle root computation
- ✅ Deterministic P2TR addresses from inscription scripts
- ✅ Clean UX with suppressed error logs during verification

See [Taproot Inscription Fix Summary](docs/taproot_inscription_fix_summary.md) for technical details.

### Unspendable Vanity Addresses
Create human-readable on-chain markers using DiMECASH character mapping:
- `DAx` prefix = Person names
- `DBx` prefix = Transport mechanism
- `DCx` prefix = Subject/topic
- `DDx/DEx` prefix = Hash references

⚠️ **Warning:** These addresses are **provably unspendable** - never send funds to them!

---

## 🧑‍💻 Advanced Usage

<details>
<summary><b>Manual RPC Configuration (click to expand)</b></summary>

If you prefer not to use the `./console` launcher, export credentials manually:

```bash
export DGB_RPC_USER="rpcuser"
export DGB_RPC_PASSWORD="rpcpass"
export DGB_RPC_HOST="127.0.0.1"
export DGB_RPC_PORT="14022"
export DGB_RPC_WALLET="taproot-lab"

# Or create ~/.enigmatic.yaml:
mkdir -p ~/.enigmatic
cat <<'YAML' > ~/.enigmatic.yaml
rpc:
  user: rpcuser
  password: rpcpass
  host: 127.0.0.1
  port: 14022
  wallet: taproot-lab
YAML

# Then use CLI directly:
enigmatic-dgb console
```

</details>

<details>
<summary><b>Bootstrap Script (legacy)</b></summary>

The `scripts/bootstrap_console_env.sh` script is available for advanced users who want environment setup without the launcher:

```bash
source scripts/bootstrap_console_env.sh
enigmatic-dgb console
```

</details>

<details>
<summary><b>Running Tests</b></summary>

```bash
# Install dev dependencies
pip install -e .[dev]

# Run full test suite
pytest

# Run specific test file
pytest tests/test_encoder.py

# Run with coverage
pytest --cov=enigmatic_dgb
```

</details>

<details>
<summary><b>CLI Command Reference</b></summary>

**Planning & Sending:**
- `plan-symbol` / `send-symbol` - Dialect-driven symbols
- `plan-sequence` / `send-sequence` - Explicit sequences
- `plan-pattern` - Custom value/fee patterns
- `plan-chain` - Multi-frame dialect chains
- `send-message` - Free-form intents

**Taproot Inscriptions:**
- `ord-wizard` - Interactive wizard
- `ord-inscribe` - Direct inscription (with --scheme taproot)
- `ord-plan-taproot` / `ord-plan-op-return` - Planning only
- `ord-decode` - Decode inscription from txid
- `ord-scan` - Scan blocks for inscriptions
- `ord-mine` - Find inscriptions in wallet UTXOs

**DTSP Messaging:**
- `dtsp-encode` - Encode message to fee sequence
- `dtsp-send` - Send DTSP handshake
- `dtsp-decode` - Decode fee sequence to message
- `dtsp-table` - Show symbol table

**Utilities:**
- `unspendable` - Generate vanity address
- `unspendable-decode` - Decode vanity address
- `list-utxos` - Inspect wallet UTXOs
- `prepare-utxos` - Pre-fragment for later use
- `watch` - Observe address activity
- `dialect` - Manage dialect files

See [`docs/TOOLING.md`](docs/TOOLING.md) for complete command documentation.

</details>

---

## 📜 History & Inspiration

From Histiaeus' scalp-tattoo courier in ancient Greece, to the Enigma machines of WWII, to Bitcoin's genesis block message, Enigmatic continues the tradition of **hiding messages in plain sight**.

The protocol name honors the codebreakers of Bletchley Park—particularly **Alan Turing**—who proved that structured patterns can be decoded even when embedded in seemingly ordinary transmissions. Enigmatic brings this principle to blockchain: transactions look economically normal while encoding multi-dimensional state vectors that peers can interpret.

---

## 🔒 Security & Deniability

Enigmatic transactions remain:
- ✅ **Economically plausible** - Normal fees, realistic amounts
- ✅ **Policy-compliant** - Standard dust limits, no exotic scripts
- ✅ **Deniable** - Patterns blend with organic usage

The [Security Model](specs/06-security-model.md) details threat assumptions, detectability bounds, and cryptographic assumptions.

---

## 📝 License

MIT License - See [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

Built with inspiration from:
- 🔐 Alan Turing and the Bletchley Park codebreakers
- 💰 Satoshi Nakamoto's Bitcoin genesis block message
- ⛏️ The DigiByte community and its 12-year blockchain heritage
- 📜 Bitcoin Ordinals theory for Taproot inscription patterns

---

## 🚀 What's Next?

See the [Expansion Roadmap](docs/expansion-roadmap.md) for planned features:
- Enhanced dialect coverage
- Wallet integration improvements
- Advanced topology patterns
- Expanded observability tools

**Ready to start?** Just run `./console` and explore! 🎉
