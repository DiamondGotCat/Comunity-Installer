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

INDEX_URL = "https://raw.githubusercontent.com/DiamondGotCat/Comunity-Installer/refs/heads/dev/index.json"
DOWNLOAD_DIR = Path("./downloads")
STATE_FILE = Path("./comin_state.json")

def fetch_index(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Failed to fetch index: {e}")
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
    # Skip if there is no download URL
    if 'url' in pkg and pkg['url']:
        local_filename = DOWNLOAD_DIR / pkg['url'].split('/')[-1]
        if local_filename.exists():
            print(f"{local_filename} already exists. Skipping.")
            return local_filename
        print(f"Downloading {pkg['name']}...")
        try:
            with requests.get(pkg['url'], stream=True) as r:
                r.raise_for_status()
                with open(local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            print(f"Download completed: {local_filename}")
            return local_filename
        except Exception as e:
            print(f"Download failed: {e}")
            return None
    else:
        # If installed via package manager, downloading is not necessary
        return None

def execute_commands(commands, cwd=None):
    for cmd in commands:
        print(f"Executing: {cmd}")
        try:
            subprocess.run(cmd, shell=True, check=True, cwd=cwd)
        except subprocess.CalledProcessError as e:
            print(f"Command '{cmd}' failed: {e}")
            sys.exit(1)

def install_package(pkg, downloaded_file, platform_key):
    print(f"Starting installation of {pkg['name']}.")
    install_commands = pkg['install_commands'].get(platform_key, [])
    if not install_commands:
        print(f"No installation commands defined for {platform_key}.")
        return
    execute_commands(install_commands, cwd=DOWNLOAD_DIR)
    print(f"Installation of {pkg['name']} completed.\n")

def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    else:
        return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def update_packages(index_packages, state, platform_key):
    print("Checking for updates...")
    for pkg in index_packages:
        pkg_name = pkg['name']
        pkg_version = pkg['version']
        if pkg_name in state:
            installed_version = state[pkg_name]['version']
            # Version comparison is unnecessary if handling only "latest"
            if pkg_version == "latest" and installed_version != "latest":
                print(f"Latest version of {pkg_name} available. Updating.")
                downloaded_file = download_package(pkg)
                if downloaded_file:
                    install_package(pkg, downloaded_file, platform_key)
                    state[pkg_name] = {
                        "version": pkg_version,
                        "installed_at": subprocess.getoutput("date")
                    }
            elif pkg_version != "latest" and installed_version != pkg_version:
                print(f"New version {pkg_version} of {pkg_name} available. Updating.")
                downloaded_file = download_package(pkg)
                if downloaded_file:
                    install_package(pkg, downloaded_file, platform_key)
                    state[pkg_name] = {
                        "version": pkg_version,
                        "installed_at": subprocess.getoutput("date")
                    }
        else:
            # New installations are not part of the update process
            continue
    save_state(state)
    print("Update process completed.\n")

def parse_arguments():
    parser = argparse.ArgumentParser(description="Comin (Community-Installer) - Package Installer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-i', '--install', nargs='+', metavar='PACKAGE', help='Specify the package name(s) to install')
    group.add_argument('-p', '--pattern', nargs='+', metavar='PATTERN', help='Specify the pattern name(s) to install')
    group.add_argument('-u', '--update', action='store_true', help='Update installed packages')
    return parser.parse_args()

def main():
    args = parse_arguments()

    index = fetch_index(INDEX_URL)
    packages = index.get('packages', [])
    patterns = index.get('patterns', {})
    if not packages:
        print("No packages available for installation.")
        sys.exit(1)

    platform_key = detect_platform()
    if platform_key == 'unknown':
        print("Unsupported platform.")
        sys.exit(1)
    print(f"Detected platform: {platform_key}\n")

    state = load_state()

    if args.install:
        selected_packages = []
        for pkg_name in args.install:
            pkg = next((p for p in packages if p['name'].lower() == pkg_name.lower()), None)
            if pkg:
                if pkg not in selected_packages:
                    selected_packages.append(pkg)
            else:
                print(f"Specified package '{pkg_name}' not found.")
        if not selected_packages:
            print("No packages selected for installation.")
            sys.exit(0)
        for pkg in selected_packages:
            downloaded_file = download_package(pkg)
            install_package(pkg, downloaded_file, platform_key)
            state[pkg['name']] = {
                "version": pkg['version'],
                "installed_at": subprocess.getoutput("date")
            }
        save_state(state)
        print("Specified package installation completed.")

    elif args.pattern:
        selected_packages = []
        for pattern_name in args.pattern:
            pkg_names = patterns.get(pattern_name.lower(), [])
            if not pkg_names:
                print(f"Specified pattern '{pattern_name}' not found.")
                continue
            for pkg_name in pkg_names:
                pkg = next((p for p in packages if p['name'].lower() == pkg_name.lower()), None)
                if pkg and pkg not in selected_packages:
                    selected_packages.append(pkg)
                elif not pkg:
                    print(f"Package '{pkg_name}' in pattern '{pattern_name}' not found.")
        if not selected_packages:
            print("No packages selected for installation.")
            sys.exit(0)
        for pkg in selected_packages:
            downloaded_file = download_package(pkg)
            install_package(pkg, downloaded_file, platform_key)
            state[pkg['name']] = {
                "version": pkg['version'],
                "installed_at": subprocess.getoutput("date")
            }
        save_state(state)
        print("Specified pattern package installation completed.")

    elif args.update:
        update_packages(packages, state, platform_key)

if __name__ == "__main__":
    main()
