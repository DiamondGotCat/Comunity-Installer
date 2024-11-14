import os
import sys
import json
import requests
import subprocess
import platform
from pathlib import Path
import shutil
import distro  # 追加: distroモジュールをインポート

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
        elif distro_name in ['suse', 'opensuse']:
            return 'suse'
        else:
            return 'unknown'
    elif system == 'windows':
        return 'windows'
    else:
        return 'unknown'

def list_packages(packages):
    print("利用可能なパッケージ:")
    for idx, pkg in enumerate(packages, start=1):
        print(f"{idx}. {pkg['name']} (バージョン: {pkg['version']})")
        print(f"   説明: {pkg.get('description', 'なし')}")
    print()

def list_patterns(patterns):
    print("利用可能なパターン:")
    for idx, (pattern, pkgs) in enumerate(patterns.items(), start=1):
        print(f"{idx}. {pattern} (含まれるパッケージ: {', '.join(pkgs)})")
    print()

def get_user_selection(num_packages, num_patterns):
    print("選択肢:")
    print("1. 個別にパッケージを選択")
    print("2. パターンを選択")
    choice = input("どの方法でインストールしますか？ (1/2): ").strip()
    selected_packages = []
    selected_patterns = []
    if choice == '1':
        selections = input("インストールしたいパッケージの番号をカンマ区切りで入力してください (例: 1,3): ")
        try:
            for part in selections.split(','):
                idx = int(part.strip())
                if 1 <= idx <= num_packages:
                    selected_packages.append(idx - 1)
                else:
                    print(f"無効な番号: {idx}")
            return selected_packages, selected_patterns
        except ValueError:
            print("入力が無効です。数字をカンマで区切って入力してください。")
            sys.exit(1)
    elif choice == '2':
        pattern_selections = input("インストールしたいパターンの番号をカンマ区切りで入力してください (例: 1,2): ")
        try:
            for part in pattern_selections.split(','):
                idx = int(part.strip())
                if 1 <= idx <= num_patterns:
                    selected_patterns.append(idx - 1)
                else:
                    print(f"無効な番号: {idx}")
            return selected_packages, selected_patterns
        except ValueError:
            print("入力が無効です。数字をカンマで区切って入力してください。")
            sys.exit(1)
    else:
        print("無効な選択です。")
        sys.exit(1)

def download_package(pkg):
    DOWNLOAD_DIR.mkdir(exist_ok=True)
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
            elif installed_version != pkg_version and pkg_version != "latest":
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

def main():
    print("Comin (Community-Installer) を起動中...\n")
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
    
    print("メニュー:")
    print("1. パッケージをインストール")
    print("2. パッケージをアップデート")
    choice = input("選択してください (1/2): ").strip()
    
    if choice == '1':
        list_packages(packages)
        list_patterns(patterns)
        selected_pkg_indices, selected_pattern_indices = get_user_selection(len(packages), len(patterns))
        selected_packages = []
        
        if selected_pkg_indices:
            for idx in selected_pkg_indices:
                selected_packages.append(packages[idx])
        
        if selected_pattern_indices:
            pattern_list = list(patterns.keys())
            for idx in selected_pattern_indices:
                pattern_name = pattern_list[idx]
                pkg_names = patterns[pattern_name]
                for pkg_name in pkg_names:
                    pkg = next((p for p in packages if p['name'] == pkg_name), None)
                    if pkg and pkg not in selected_packages:
                        selected_packages.append(pkg)
        
        if not selected_packages:
            print("インストールするパッケージが選択されませんでした。")
            sys.exit(0)
        
        for pkg in selected_packages:
            downloaded_file = download_package(pkg)
            if downloaded_file:
                install_package(pkg, downloaded_file, platform_key)
                state[pkg['name']] = {
                    "version": pkg['version'],
                    "installed_at": subprocess.getoutput("date")
                }
        
        save_state(state)
        print("全ての選択されたパッケージのインストールが完了しました。")
    
    elif choice == '2':
        update_packages(packages, state, platform_key)
    else:
        print("無効な選択です。")
        sys.exit(1)

if __name__ == "__main__":
    main()
