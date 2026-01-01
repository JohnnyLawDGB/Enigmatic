# Enigmatic Console Launcher

## Quick Start

Simply run the launcher script from the Enigmatic project root:

```bash
./console
```

The script will:
1. ✅ Check if RPC credentials are already in your environment
2. ✅ Prompt for credentials if needed (with smart defaults)
3. ✅ Optionally save credentials to `~/.enigmatic.yaml` for future use
4. ✅ Activate the Python virtual environment (`.venv`)
5. ✅ Export all RPC variables to the environment
6. ✅ Launch the Enigmatic console with the beautiful splash screen

## First Time Setup

When you run `./console` for the first time, you'll be prompted:

```
╔════════════════════════════════════════╗
║  Enigmatic Console Environment Setup  ║
╚════════════════════════════════════════╝

RPC credentials not found. Please enter your DigiByte node details:

RPC Username: yourusername
RPC Password: ********
RPC Host [127.0.0.1]:
RPC Port [14022]:

✓ RPC credentials configured

No ~/.enigmatic.yaml found
Save credentials to ~/.enigmatic.yaml for future use? [y/N]: y
✓ Saved to ~/.enigmatic.yaml

Activating virtual environment...
Launching Enigmatic Console...
```

## Subsequent Runs

After the first time, if you saved credentials to `~/.enigmatic.yaml`, the script will:

```
✓ RPC credentials found in environment
  User: yourusername
  Host: 127.0.0.1:14022

Use existing credentials? [Y/n]:
Using existing RPC configuration

Launching Enigmatic Console...
```

## Environment Variables

The script exports these variables before launching:
- `DGB_RPC_USER` - RPC username
- `DGB_RPC_PASSWORD` - RPC password
- `DGB_RPC_HOST` - RPC host (default: 127.0.0.1)
- `DGB_RPC_PORT` - RPC port (default: 14022)

## Manual Override

You can also set these manually before running:

```bash
export DGB_RPC_USER=myuser
export DGB_RPC_PASSWORD=mypass
export DGB_RPC_HOST=127.0.0.1
export DGB_RPC_PORT=14022

./console
```

The script will detect the existing environment variables and ask if you want to use them.

## Configuration File

Credentials can be saved in `~/.enigmatic.yaml`:

```yaml
rpc:
  host: 127.0.0.1
  port: 14022
  user: yourusername
  password: yourpassword
```

## Troubleshooting

### "Please run this script from the Enigmatic project root directory"
Make sure you're in the directory containing `enigmatic_dgb/`:
```bash
cd /path/to/Enigmatic
./console
```

### "No .venv directory found"
Create and activate a virtual environment first:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Then run `./console` - it will activate `.venv` automatically.

### Permission denied
Make the script executable:
```bash
chmod +x console
```

## Features

- 🎨 **Color-coded output** for easy reading
- 🔒 **Password masking** when entering credentials
- 💾 **Smart defaults** (127.0.0.1:14022)
- 📝 **Optional config save** to `~/.enigmatic.yaml`
- ♻️ **Reuses existing credentials** from environment or config file
- 🐍 **Auto-activates** virtual environment if present
- ✅ **Pre-flight checks** to ensure proper setup

## No More Forgetting!

Never forget to export your RPC credentials again - just run `./console` and you're ready to go! 🚀
