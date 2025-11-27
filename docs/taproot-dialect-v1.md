# Enigmatic Taproot Dialect v1

## Goal
Enigmatic Taproot Dialect v1 defines a simple, conventional inscription format for DigiByte Taproot outputs. It standardizes how Enigmatic embeds typed payloads in Taproot script paths without altering consensus rules.

## Script-path layout
Pseudo-script for an inscription leaf:

```
OP_FALSE
OP_IF
  <"ENIG">             # 4-byte magic for the Enigmatic Taproot dialect
  <version_byte>        # 1 byte, currently 0x01
  <content_type_str>    # 1-byte length prefix + UTF-8 bytes, e.g. "text/plain"
  <payload_bytes>       # raw payload (text, JSON, binary, stego, etc.)
OP_ENDIF
# plus whatever spend satisfaction script is necessary
```

### Fields
- **Magic (`ENIG`)**: Identifies the Enigmatic Taproot dialect and guards against accidental misparsing.
- **Version (1 byte)**: Enables future dialect evolution. Version `0x01` corresponds to this document.
- **Content type (length-prefixed UTF-8)**: A MIME-like string describing the payload (examples: `text/plain`, `application/json`). The length prefix is a single byte, limiting the header to 255 bytes.
- **Payload bytes**: The raw inscription content. Applications SHOULD weigh payload size against fee costs and on-chain footprint.

Implementations SHOULD use `encode_enig_taproot_payload` and `decode_enig_taproot_payload` in `enigmatic_dgb.ordinals` to preserve the exact header layout. Version bumps will be reflected in those helpers first.

## Notes
Version 1 intentionally keeps the envelope minimal: a fixed magic, 1-byte version, a short content type header, and arbitrary payload bytes. Larger payloads increase transaction fees and may face relay/policy limits; authors should account for size and economic impacts when crafting inscriptions.

## Discovering my inscriptions
The experimental CLI can search for inscriptions that land in your wallet's UTXOs or a set of explicit addresses using `ord-mine`:

```bash
# Scan a wallet's UTXOs between block 3,000,000 and 3,010,000
enigmatic-dgb ord-mine --wallet mywallet --start-height 3000000 --end-height 3010000 --limit 25

# Scan explicit addresses with JSON output
enigmatic-dgb ord-mine --address dgb1qexample... --address dgb1qanother... --json
```

The current implementation performs a straightforward block walk using the same heuristics as `ord-scan`. Future revisions will add smarter indexing and caching once the patterns stabilize.
