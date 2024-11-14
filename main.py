import os
import sys
import json
import requests
import subprocess
import platform
from pathlib import Path
import shutil
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
        print(f"インデックスの取得に失敗しました: {e}")
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
    # ダウンロードURLがない場合はスキップ
    if 'url' in pkg and pkg['url']:
        local_filename = DOWNLOAD_DIR / pkg['url'].split('/')[-1]
        if local_filename.exists():
            print(f"{local_filename} は既に存在します。スキップします。")
            return local_filename
        print(f"{pkg['name']} をダウンロード中...")
        try:
            with requests.get(pkg['url'], stream=True) as r:
                r.raise_for_status()
                with open(local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            print(f"ダウンロード完了: {local_filename}")
            return local_filename
        except Exception as e:
            print(f"ダウンロードに失敗しました: {e}")
            return None
    else:
        # パッケージマネージャー経由でインストールする場合、ダウンロードは不要
        return None

def execute_commands(commands, cwd=None):
    for cmd in commands:
        print(f"実行中: {cmd}")
        try:
            subprocess.run(cmd, shell=True, check=True, cwd=cwd)
        except subprocess.CalledProcessError as e:
            print(f"コマンド '{cmd}' の実行に失敗しました: {e}")
            sys.exit(1)

def install_package(pkg, downloaded_file, platform_key):
    print(f"{pkg['name']} のインストールを開始します。")
    install_commands = pkg['install_commands'].get(platform_key, [])
    if not install_commands:
        print(f"{platform_key} 向けのインストールコマンドが定義されていません。")
        return
    execute_commands(install_commands, cwd=DOWNLOAD_DIR)
    print(f"{pkg['name']} のインストールが完了しました。\n")

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
    print("アップデートを確認しています...")
    for pkg in index_packages:
        pkg_name = pkg['name']
        pkg_version = pkg['version']
        if pkg_name in state:
            installed_version = state[pkg_name]['version']
            # "latest" のみを扱う場合、バージョン比較は不要
            if pkg_version == "latest" and installed_version != "latest":
                print(f"{pkg_name} の最新バージョンが利用可能です。アップデートします。")
                downloaded_file = download_package(pkg)
                if downloaded_file:
                    install_package(pkg, downloaded_file, platform_key)
                    state[pkg_name] = {
                        "version": pkg_version,
                        "installed_at": subprocess.getoutput("date")
                    }
            elif pkg_version != "latest" and installed_version != pkg_version:
                print(f"{pkg_name} の新しいバージョン {pkg_version} が利用可能です。アップデートします。")
                downloaded_file = download_package(pkg)
                if downloaded_file:
                    install_package(pkg, downloaded_file, platform_key)
                    state[pkg_name] = {
                        "version": pkg_version,
                        "installed_at": subprocess.getoutput("date")
                    }
        else:
            # 新規インストールはアップデート対象外
            continue
    save_state(state)
    print("アップデート処理が完了しました。\n")

def parse_arguments():
    parser = argparse.ArgumentParser(description="Comin (Community-Installer) - パッケージインストーラー")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-i', '--install', nargs='+', metavar='PACKAGE', help='インストールするパッケージ名を指定')
    group.add_argument('-p', '--pattern', nargs='+', metavar='PATTERN', help='インストールするパターン名を指定')
    group.add_argument('-u', '--update', action='store_true', help='インストール済みパッケージをアップデート')
    return parser.parse_args()

def main():
    args = parse_arguments()

    index = fetch_index(INDEX_URL)
    packages = index.get('packages', [])
    patterns = index.get('patterns', {})
    if not packages:
        print("インストール可能なパッケージが見つかりません。")
        sys.exit(1)

    platform_key = detect_platform()
    if platform_key == 'unknown':
        print("サポートされていないプラットフォームです。")
        sys.exit(1)
    print(f"検出されたプラットフォーム: {platform_key}\n")

    state = load_state()

    if args.install:
        selected_packages = []
        for pkg_name in args.install:
            pkg = next((p for p in packages if p['name'].lower() == pkg_name.lower()), None)
            if pkg:
                if pkg not in selected_packages:
                    selected_packages.append(pkg)
            else:
                print(f"指定されたパッケージ '{pkg_name}' は見つかりません。")
        if not selected_packages:
            print("インストールするパッケージが選択されませんでした。")
            sys.exit(0)
        for pkg in selected_packages:
            downloaded_file = download_package(pkg)
            install_package(pkg, downloaded_file, platform_key)
            state[pkg['name']] = {
                "version": pkg['version'],
                "installed_at": subprocess.getoutput("date")
            }
        save_state(state)
        print("指定されたパッケージのインストールが完了しました。")

    elif args.pattern:
        selected_packages = []
        for pattern_name in args.pattern:
            pkg_names = patterns.get(pattern_name.lower(), [])
            if not pkg_names:
                print(f"指定されたパターン '{pattern_name}' は見つかりません。")
                continue
            for pkg_name in pkg_names:
                pkg = next((p for p in packages if p['name'].lower() == pkg_name.lower()), None)
                if pkg and pkg not in selected_packages:
                    selected_packages.append(pkg)
                elif not pkg:
                    print(f"パターン '{pattern_name}' に含まれるパッケージ '{pkg_name}' が見つかりません。")
        if not selected_packages:
            print("インストールするパッケージが選択されませんでした。")
            sys.exit(0)
        for pkg in selected_packages:
            downloaded_file = download_package(pkg)
            install_package(pkg, downloaded_file, platform_key)
            state[pkg['name']] = {
                "version": pkg['version'],
                "installed_at": subprocess.getoutput("date")
            }
        save_state(state)
        print("指定されたパターンのパッケージのインストールが完了しました。")

    elif args.update:
        update_packages(packages, state, platform_key)

if __name__ == "__main__":
    main()
