#!/usr/bin/env python3
"""Update the pinned WAHA image when its latest stable ARM image is published."""

import argparse
import datetime
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

RELEASE_URL = "https://api.github.com/repos/devlikeapro/waha/releases/latest"
TAG_URL = "https://hub.docker.com/v2/repositories/devlikeapro/waha/tags/"
VERSION = r"[0-9]+\.[0-9]+\.[0-9]+"
WAHA_VERSION = r"[0-9]{4}\.[0-9]+\.[0-9]+"
DIGEST = r"sha256:[0-9a-f]{64}"


def get_json(url):
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ha-waha-addon-updater"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def version_tuple(version):
    if not isinstance(version, str) or not re.fullmatch(VERSION, version, flags=re.ASCII):
        raise ValueError(f"Invalid version: {version!r}")
    return tuple(map(int, version.split(".")))


def update(root, fetch=get_json, today=None):
    release = fetch(RELEASE_URL)
    if not isinstance(release, dict) or type(release.get("draft")) is not bool or type(release.get("prerelease")) is not bool:
        raise ValueError("Invalid release response")
    if release["draft"] or release["prerelease"]:
        return None
    candidate = release.get("tag_name")
    if not isinstance(candidate, str) or not re.fullmatch(WAHA_VERSION, candidate):
        raise ValueError(f"Invalid WAHA release tag: {candidate!r}")
    candidate_parts = version_tuple(candidate)

    directory = root / "waha"
    docker_path, config_path, changelog_path = (directory / name for name in ("Dockerfile", "config.yaml", "CHANGELOG.md"))
    docker, config, changelog = (path.read_text(encoding="utf-8") for path in (docker_path, config_path, changelog_path))
    from_lines = re.findall(r"^FROM\s+.*$", docker, re.MULTILINE | re.IGNORECASE)
    if len(from_lines) != 1:
        raise ValueError("Expected exactly one Dockerfile FROM")
    image = re.fullmatch(rf"FROM devlikeapro/waha:(noweb-arm-({WAHA_VERSION}))(?:@{DIGEST})?", from_lines[0])
    if not image:
        raise ValueError("Unexpected Dockerfile base image")
    old_tag, current = image.group(1), image.group(2)
    if candidate_parts <= version_tuple(current):
        return None

    tag = "noweb-arm-" + candidate
    try:
        payload = fetch(TAG_URL + tag)
    except urllib.error.HTTPError as error:
        error.close()
        if error.code == 404:
            return None
        raise
    if not isinstance(payload, dict) or payload.get("name") != tag:
        raise ValueError("Unexpected Docker Hub tag response")
    images = payload.get("images")
    if not isinstance(images, list) or not any(isinstance(image, dict) and image.get("os") == "linux" and image.get("architecture") == "arm64" and image.get("status") == "active" for image in images):
        raise ValueError("No active linux/arm64 image")
    digest = payload.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(DIGEST, digest, re.ASCII):
        raise ValueError("Invalid Docker Hub manifest digest")

    versions = list(re.finditer(rf'^version: "({VERSION})"$', config, re.MULTILINE | re.ASCII))
    if len(versions) != 1 or len(re.findall(r"^version\s*:", config, re.MULTILINE)) != 1:
        raise ValueError("Expected exactly one quoted add-on version")
    old_version = versions[0].group(1)
    major, minor, patch = version_tuple(old_version)
    new_version = f"{major}.{minor}.{patch + 1}"
    headers = list(re.finditer(rf"^## ({VERSION}) - [0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$", changelog, re.MULTILINE | re.ASCII))
    all_headers = list(re.finditer(r"^## ", changelog, re.MULTILINE))
    if not changelog.startswith("# Changelog\n") or not headers or not all_headers or headers[0].start() != all_headers[0].start() or headers[0].group(1) != old_version or any(header.group(1) == new_version for header in headers):
        raise ValueError("Unexpected changelog structure or version")
    date = today or datetime.datetime.now(datetime.timezone.utc).date()
    entry = (f"## {new_version} - {date.isoformat()}\n\n"
             f"- Update WAHA from `{old_tag}` to `{tag}`. "
             f"[Upstream release](https://github.com/devlikeapro/waha/releases/tag/{candidate}).\n\n")
    new_docker = docker.replace(from_lines[0], f"FROM devlikeapro/waha:{tag}@{digest}", 1)
    new_config = config[:versions[0].start(1)] + new_version + config[versions[0].end(1):]
    new_changelog = changelog[:headers[0].start()] + entry + changelog[headers[0].start():]
    for path, content in zip((docker_path, config_path, changelog_path), (new_docker, new_config, new_changelog)):
        path.write_text(content, encoding="utf-8")
    return candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        candidate = update(args.root, get_json)
    except (OSError, ValueError, TypeError) as error:
        print(f"WAHA update failed: {error}", file=sys.stderr)
        return 1
    if candidate is not None:
        print(candidate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
