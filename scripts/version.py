#!/usr/bin/env python3
"""
Simple version management for uv-based projects.
Updates version in pyproject.toml and syncs to __init__.py
"""

import re
import sys
import argparse
import subprocess
from pathlib import Path


def get_current_version():
    """Read version from pyproject.toml"""
    pyproject_toml = Path("pyproject.toml")
    if not pyproject_toml.exists():
        raise FileNotFoundError("pyproject.toml not found")
    
    content = pyproject_toml.read_text()
    match = re.search(r'^version = "([^"]+)"', content, re.MULTILINE)
    if not match:
        raise ValueError("Version not found in pyproject.toml")
    
    return match.group(1)


def update_version(new_version):
    """Update version in pyproject.toml and __init__.py"""
    # Update pyproject.toml
    pyproject_toml = Path("pyproject.toml")
    content = pyproject_toml.read_text()
    
    new_content = re.sub(
        r'^version = "[^"]+"',
        f'version = "{new_version}"',
        content,
        flags=re.MULTILINE
    )
    
    if content == new_content:
        raise ValueError("Version line not found in pyproject.toml")
    
    pyproject_toml.write_text(new_content)
    print(f"✅ Updated version to {new_version} in pyproject.toml")
    
    # Update __init__.py
    init_file = Path("dynamo_news/__init__.py")
    if init_file.exists():
        init_content = init_file.read_text()
        new_init_content = re.sub(
            r'^__version__ = "[^"]+"',
            f'__version__ = "{new_version}"',
            init_content,
            flags=re.MULTILINE
        )
        
        if new_init_content != init_content:
            init_file.write_text(new_init_content)
            print(f"✅ Updated __version__ to {new_version} in dynamo_news/__init__.py")


def bump_version(current_version, bump_type):
    """Bump version based on type"""
    parts = current_version.split(".")
    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {current_version}")
    
    major, minor, patch = map(int, parts)
    
    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")
    
    return f"{major}.{minor}.{patch}"


def check_tag_exists(version):
    """Check if git tag exists"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", f"v{version}"],
            capture_output=True,
            check=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def main():
    parser = argparse.ArgumentParser(description="Version management")
    subparsers = parser.add_subparsers(dest="command")
    
    # Show current version
    subparsers.add_parser("show", help="Show current version")
    
    # Set version
    set_parser = subparsers.add_parser("set", help="Set version")
    set_parser.add_argument("version", help="Version to set")
    
    # Bump version
    bump_parser = subparsers.add_parser("bump", help="Bump version")
    bump_parser.add_argument("type", choices=["major", "minor", "patch"])
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == "show":
            version = get_current_version()
            print(version)
        
        elif args.command == "set":
            if check_tag_exists(args.version):
                print(f"⚠️  Warning: Tag v{args.version} already exists")
            
            update_version(args.version)
            print(f"\n📝 Next steps:")
            print(f"1. git add dynamo_news")
            print(f"2. git commit -m 'Bump version to {args.version}'")
            print(f"3. git push origin main")
        
        elif args.command == "bump":
            current = get_current_version()
            new_version = bump_version(current, args.type)
            
            if check_tag_exists(new_version):
                print(f"⚠️  Warning: Tag v{new_version} already exists")
            
            update_version(new_version)
            print(f"Version bumped: {current} → {new_version}")
            print(f"\n📝 Next steps:")
            print(f"1. git add dynamo_news")
            print(f"2. git commit -m 'Bump version to {new_version}'")
            print(f"3. git push origin main")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
