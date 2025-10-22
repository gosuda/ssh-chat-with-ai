"""
Quick demo runner for SSH Chat with AI.

This script helps you quickly run the system by:
1. Starting the SSH server
2. Starting the AI client

Usage:
    python demo.py              # Interactive demo
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Paths
PROJECT_ROOT = Path(__file__).parent.parent  # Go up one level from tests/
SSH_CHAT_DIR = PROJECT_ROOT / "ssh-chat"
AI_SENDER_DIR = PROJECT_ROOT / "stream-ai-message-sender"


def load_env_file(env_path: Path) -> dict:
    """Load environment variables from .env file."""
    env_vars = {}
    if env_path.exists():
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            env_vars[key.strip()] = value.strip()
        except Exception as e:
            pass  # Silently fail if .env file can't be read
    return env_vars


def get_gemini_api_key() -> Optional[str]:
    """Get GEMINI_API_KEY from .env file or environment variable."""
    # First try to load from .env file
    env_file = AI_SENDER_DIR / ".env"
    env_vars = load_env_file(env_file)
    api_key = env_vars.get("GEMINI_API_KEY")
    
    # If not found or is placeholder, try environment variable
    if not api_key or api_key == "your-gemini-api-key-here":
        api_key = os.getenv("GEMINI_API_KEY")
    
    return api_key if api_key else None


class Colors:
    """ANSI color codes."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print a colored header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text:^60}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.END}\n")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.END}")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}❌ {text}{Colors.END}")


def check_environment():
    """Check if environment is properly set up."""
    print_header("Environment Check")
    
    issues = []
    
    # Check Go
    try:
        result = subprocess.run(["go", "version"], capture_output=True, text=True)
        if result.returncode == 0:
            print_success(f"Go installed: {result.stdout.strip()}")
        else:
            issues.append("Go not working properly")
    except FileNotFoundError:
        issues.append("Go not installed")
        print_error("Go not found")
    
    # Check Python
    print_success(f"Python: {sys.version.split()[0]}")
    
    # Check Docker
    try:
        result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print_success(f"Docker installed: {result.stdout.strip()}")
        else:
            issues.append("Docker not working properly")
    except FileNotFoundError:
        issues.append("Docker not installed")
        print_error("Docker not found - install from https://www.docker.com/")
    
    # Check Docker Compose
    try:
        result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True)
        if result.returncode == 0:
            print_success(f"Docker Compose installed: {result.stdout.strip()}")
        else:
            issues.append("Docker Compose not working properly")
    except FileNotFoundError:
        issues.append("Docker Compose not available")
        print_error("Docker Compose not found")
    
    # Check GEMINI_API_KEY
    if get_gemini_api_key():
        print_success("GEMINI_API_KEY is set")
    else:
        issues.append("GEMINI_API_KEY not set")
        print_warning("GEMINI_API_KEY not set - AI features will not work")
    
    # Check required files
    required_files = [
        SSH_CHAT_DIR / "main.go",
        SSH_CHAT_DIR / "host.key",
        AI_SENDER_DIR / "main.py",
        AI_SENDER_DIR / "certs" / "ai_grpc_client.key",
        AI_SENDER_DIR / "certs" / "ai_grpc_client.pub",
    ]
    
    for file in required_files:
        if file.exists():
            print_success(f"Found: {file.name}")
        else:
            issues.append(f"Missing: {file}")
            print_error(f"Missing: {file}")
    
    if issues:
        print_error(f"\n{len(issues)} issue(s) found:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print_success("\n✨ Environment looks good!")
        return True


def build_ssh_server():
    """Build the SSH server."""
    print_header("Building SSH Server")
    print_info("Building Go server...")
    
    result = subprocess.run(
        ["go", "build", "-o", "ssh-chat-server", "."],
        cwd=SSH_CHAT_DIR,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print_success("SSH server built successfully")
        return True
    else:
        print_error("Failed to build SSH server")
        print(result.stderr)
        return False


def build_docker_image():
    """Build Docker image for AI message sender."""
    print_header("Building Docker Image")
    print_info("Building stream-ai-message-sender Docker image...")
    
    result = subprocess.run(
        ["docker", "build", "-t", "stream-ai-message-sender", "."],
        cwd=AI_SENDER_DIR,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print_success("Docker image built successfully")
        return True
    else:
        print_error("Failed to build Docker image")
        print(result.stderr)
        return False


def create_docker_network():
    """Create Docker network if it doesn't exist."""
    # Check if network exists
    result = subprocess.run(
        ["docker", "network", "ls", "--format", "{{.Name}}"],
        capture_output=True,
        text=True
    )
    
    if "ssh-chat-network" not in result.stdout:
        print_info("Creating Docker network 'ssh-chat-network'...")
        result = subprocess.run(
            ["docker", "network", "create", "ssh-chat-network"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            print_success("Docker network created")
        else:
            print_warning("Could not create Docker network")
    else:
        print_success("Docker network already exists")


def stop_docker_compose():
    """Stop docker-compose services if running."""
    result = subprocess.run(
        ["docker", "compose", "ps", "-q"],
        cwd=AI_SENDER_DIR,
        capture_output=True,
        text=True
    )
    
    if result.stdout.strip():
        print_info("Stopping existing docker-compose services...")
        subprocess.run(
            ["docker", "compose", "down"],
            cwd=AI_SENDER_DIR,
            capture_output=True
        )


def interactive_demo():
    """Run interactive demo."""
    print_header("SSH Chat with AI - Interactive Demo")
    
    print(f"""
{Colors.CYAN}This demo will:
1. Start the SSH chat server (port 2222)
2. Start the AI message sender in Docker (connects to port 3333)
3. Wait for you to connect via SSH

To connect, open a new terminal and run:
{Colors.BOLD}ssh -p 2222 yourname@localhost{Colors.END}{Colors.CYAN}

Commands in chat:
- @AI <message>  : Mention AI to get a response
- Ask questions with ? : AI may respond
- Regular chat messages work too!

Press Ctrl+C to stop all services.
{Colors.END}
""")
    
    input(f"{Colors.YELLOW}Press Enter to start...{Colors.END}")
    
    # Prepare Docker environment
    if get_gemini_api_key():
        create_docker_network()
        
        # Stop any existing docker-compose services
        stop_docker_compose()
    
    # Start SSH server
    print_info("Starting SSH server...")
    ssh_process = subprocess.Popen(
        ["go", "run", "main.go"],
        cwd=SSH_CHAT_DIR
    )
    
    print_info("Waiting for SSH server to start...")
    time.sleep(3)
    
    # Start AI client in Docker using docker-compose
    ai_started = False
    if get_gemini_api_key():
        print_info("Starting AI client using docker-compose...")
        
        result = subprocess.run(
            ["docker", "compose", "up", "-d", "--build"],
            cwd=AI_SENDER_DIR,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            ai_started = True
            print_success("AI client started using docker-compose")
            print_info("Waiting for AI client to connect...")
            time.sleep(5)
        else:
            print_error("Failed to start AI client")
            print(result.stderr)
    else:
        print_warning("Skipping AI client (no API key)")
    
    print_success("\n🚀 Services started!")
    print(f"\n{Colors.GREEN}Connect now with:{Colors.END}")
    print(f"{Colors.BOLD}ssh -p 2222 yourname@localhost{Colors.END}\n")
    
    if ai_started:
        print_info(f"AI client logs: docker logs -f stream-ai-message-sender")
    
    try:
        ssh_process.wait()
    except KeyboardInterrupt:
        print_info("\n\nShutting down...")
        ssh_process.terminate()
        
        if ai_started:
            print_info("Stopping Docker containers...")
            subprocess.run(
                ["docker", "compose", "down"],
                cwd=AI_SENDER_DIR,
                capture_output=True
            )
        
        ssh_process.wait()
        print_success("Services stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="SSH Chat with AI - Demo Runner"
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Skip building SSH server"
    )
    
    args = parser.parse_args()
    
    # Check environment
    if not check_environment():
        print_error("\n❌ Environment check failed. Please fix issues above.")
        return 1
    
    # Build server if needed
    if not args.no_build:
        if not build_ssh_server():
            print_error("\n❌ Build failed")
            return 1
        
        # Build Docker image for AI sender
        if get_gemini_api_key():
            if not build_docker_image():
                print_error("\n❌ Docker build failed")
                return 1
    
    # Run interactive demo
    interactive_demo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
