#!/usr/bin/env python3
import os
import sys
import json
import requests
import subprocess
import platform
from pathlib import Path
import distro
import argparse
from rich.console import Console
from rich.progress import Progress, DownloadColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table
from rich.prompt import Prompt
from rich.panel import Panel

INDEX_URL = "https://raw.githubusercontent.com/DiamondGotCat/Comunity-Installer/refs/heads/dev/index.json"
DOWNLOAD_DIR = Path("./downloads")
STATE_FILE = Path("./comin_state.json")

console = Console()

def fetch_index(url):
    try:
        console.log("[bold cyan]Fetching index...[/bold cyan]")
        response = requests.get(url)
        response.raise_for_status()
        index = response.json()
        console.log("[bold green]Index fetched successfully.[/bold green]")
        return index
    except Exception as e:
        console.print(f"[bold red]Failed to fetch index: {e}[/bold red]")
        sys.exit(1)

def detect_platform():
    system = platform.system().lower()
    if system == 'darwin':
        return 'macos'
    elif system == 'linux':
        distro_name = distro.id().lower()
        if distro_name in ['debian', 'ubuntu', 'linuxmint']:
            return 'debian'
        elif distro_name in ['fedora', 'centos', 'rhel']:
            return 'fedora'
        elif distro_name.startswith('opensuse') or distro_name in ['suse', 'sles']:
            return 'suse'
        else:
            return 'unknown'
    elif system == 'windows':
        return 'windows'
    else:
        return 'unknown'

def download_package(pkg):
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    if 'url' in pkg and pkg['url']:
        local_filename = DOWNLOAD_DIR / pkg['url'].split('/')[-1]
        if local_filename.exists():
            console.print(f"[yellow]{local_filename}[/yellow] already exists. Skipping download.")
            return local_filename
        console.print(f"[bold blue]Downloading {pkg['name']}...[/bold blue]")
        try:
            with requests.get(pkg['url'], stream=True) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                with Progress(
                    "[progress.description]{task.description}",
                    BarColumn(),
                    DownloadColumn(),
                    "[progress.percentage]{task.percentage:>3.1f}%",
                    "•",
                    TimeRemainingColumn(),
                    console=console
                ) as progress:
                    task = progress.add_task("Downloading...", total=total)
                    with open(local_filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                progress.update(task, advance=len(chunk))
            console.print(f"[bold green]Download completed: {local_filename}[/bold green]")
            return local_filename
        except Exception as e:
            console.print(f"[bold red]Download failed: {e}[/bold red]")
            return None
    else:
        # If installed via package manager, downloading is not necessary
        return None

def execute_commands(commands, cwd=None):
    for cmd in commands:
        console.print(f"[bold magenta]Executing: {cmd}[/bold magenta]")
        try:
            subprocess.run(cmd, shell=True, check=True, cwd=cwd)
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]Command '{cmd}' failed: {e}[/bold red]")
            sys.exit(1)

def install_package(pkg, downloaded_file, platform_key):
    console.print(f"[bold green]Starting installation of {pkg['name']}.[/bold green]")
    install_commands = pkg['install_commands'].get(platform_key, [])
    if not install_commands:
        console.print(f"[bold yellow]No installation commands defined for {platform_key}.[/bold yellow]")
        return
    execute_commands(install_commands, cwd=DOWNLOAD_DIR)
    console.print(f"[bold green]Installation of {pkg['name']} completed.\n[/bold green]")

def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                console.log("[bold green]Loaded existing state.[/bold green]")
                return state
        except Exception:
            console.print("[bold yellow]Failed to load state file. Starting fresh.[/bold yellow]")
            return {}
    else:
        return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)
    console.log("[bold green]State saved.[/bold green]")

def update_packages(index_packages, state, platform_key):
    console.print("[bold blue]Checking for updates...[/bold blue]")
    updates_available = False
    for pkg in index_packages:
        pkg_name = pkg['name']
        pkg_version = pkg['version']
        if pkg_name in state:
            installed_version = state[pkg_name]['version']
            if pkg_version == "latest" and installed_version != "latest":
                console.print(f"[bold yellow]Latest version of {pkg_name} available. Updating.[/bold yellow]")
                downloaded_file = download_package(pkg)
                if downloaded_file:
                    install_package(pkg, downloaded_file, platform_key)
                    state[pkg_name] = {
                        "version": pkg_version,
                        "installed_at": subprocess.getoutput("date")
                    }
                    updates_available = True
            elif pkg_version != "latest" and installed_version != pkg_version:
                console.print(f"[bold yellow]New version {pkg_version} of {pkg_name} available. Updating.[/bold yellow]")
                downloaded_file = download_package(pkg)
                if downloaded_file:
                    install_package(pkg, downloaded_file, platform_key)
                    state[pkg_name] = {
                        "version": pkg_version,
                        "installed_at": subprocess.getoutput("date")
                    }
                    updates_available = True
    if updates_available:
        save_state(state)
        console.print("[bold green]Update process completed.[/bold green]\n")
    else:
        console.print("[bold green]All packages are up to date.[/bold green]\n")

def parse_arguments():
    parser = argparse.ArgumentParser(description="Comin (Community-Installer) - Package Installer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-i', '--install', nargs='+', metavar='PACKAGE', help='Specify the package name(s) to install')
    group.add_argument('-p', '--pattern', nargs='+', metavar='PATTERN', help='Specify the pattern name(s) to install')
    group.add_argument('-u', '--update', action='store_true', help='Update installed packages')
    return parser.parse_args()

def display_packages(packages):
    table = Table(title="Available Packages", show_header=True, header_style="bold magenta")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Version", style="green")
    table.add_column("Description", style="white")
    for pkg in packages:
        table.add_row(pkg['name'], pkg['version'], pkg.get('description', 'No description'))
    console.print(table)

def display_patterns(patterns):
    table = Table(title="Available Patterns", show_header=True, header_style="bold magenta")
    table.add_column("Pattern Name", style="cyan", no_wrap=True)
    table.add_column("Packages Included", style="green")
    for pattern, pkgs in patterns.items():
        table.add_row(pattern, ", ".join(pkgs))
    console.print(table)

def main():
    args = parse_arguments()

    index = fetch_index(INDEX_URL)
    packages = index.get('packages', [])
    patterns = index.get('patterns', {})
    if not packages:
        console.print("[bold red]No packages available for installation.[/bold red]")
        sys.exit(1)

    platform_key = detect_platform()
    if platform_key == 'unknown':
        console.print("[bold red]Unsupported platform.[/bold red]")
        sys.exit(1)
    console.print(f"[bold green]Detected platform: {platform_key}[/bold green]\n")

    state = load_state()

    if args.install:
        selected_packages = []
        for pkg_name in args.install:
            pkg = next((p for p in packages if p['name'].lower() == pkg_name.lower()), None)
            if pkg:
                if pkg not in selected_packages:
                    selected_packages.append(pkg)
            else:
                console.print(f"[bold red]Specified package '{pkg_name}' not found.[/bold red]")
        if not selected_packages:
            console.print("[bold yellow]No packages selected for installation.[/bold yellow]")
            sys.exit(0)
        
        display_packages(selected_packages)

        for pkg in selected_packages:
            downloaded_file = download_package(pkg)
            install_package(pkg, downloaded_file, platform_key)
            state[pkg['name']] = {
                "version": pkg['version'],
                "installed_at": subprocess.getoutput("date")
            }
        save_state(state)
        console.print("[bold green]Specified package installation completed.[/bold green]")

    elif args.pattern:
        selected_packages = []
        for pattern_name in args.pattern:
            pkg_names = patterns.get(pattern_name.lower(), [])
            if not pkg_names:
                console.print(f"[bold red]Specified pattern '{pattern_name}' not found.[/bold red]")
                continue
            for pkg_name in pkg_names:
                pkg = next((p for p in packages if p['name'].lower() == pkg_name.lower()), None)
                if pkg and pkg not in selected_packages:
                    selected_packages.append(pkg)
                elif not pkg:
                    console.print(f"[bold red]Package '{pkg_name}' in pattern '{pattern_name}' not found.[/bold red]")
        if not selected_packages:
            console.print("[bold yellow]No packages selected for installation.[/bold yellow]")
            sys.exit(0)
        
        display_packages(selected_packages)

        for pkg in selected_packages:
            downloaded_file = download_package(pkg)
            install_package(pkg, downloaded_file, platform_key)
            state[pkg['name']] = {
                "version": pkg['version'],
                "installed_at": subprocess.getoutput("date")
            }
        save_state(state)
        console.print("[bold green]Specified pattern package installation completed.[/bold green]")

    elif args.update:
        update_packages(packages, state, platform_key)

if __name__ == "__main__":
    main()
