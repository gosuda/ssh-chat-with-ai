# SSH Chat Demo Tools

This directory contains demo and testing tools for the SSH Chat with AI project.

## Files

- `demo.py` - Main demo script that starts the SSH server and AI client
- `send_dummy.py` - Dummy client that sends automated messages for testing
- `dummy.py` - Contains dummy message data

## Setup

This directory uses `uv` for Python environment management.

### Install uv (if not already installed)

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Install dependencies

```bash
cd tests
uv sync
```

## Usage

### Running the demo

To run the full demo with SSH server and AI client:

```bash
uv run python demo.py
```

Wait for the server to start and warm up (approximately 5-10 seconds), then you can:
1. Connect via SSH: `ssh -p 2222 yourname@localhost`
2. Run the dummy message sender in another terminal to simulate automated chat

### Running the dummy message sender

After the demo server has warmed up, run in a separate terminal:

```bash
cd tests
uv run python send_dummy.py
```

This will connect as a user and send automated messages every 10 seconds.

## Options

### Demo script options

- `--no-build` - Skip building the SSH server (useful if already built)

Example:
```bash
uv run python demo.py --no-build
```
