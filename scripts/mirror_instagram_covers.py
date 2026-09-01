#!/usr/bin/env python3
"""Mirror public Instagram cover images from Meta Graph into this repository.

The runner is intentionally outside the RU hosting network, where Meta CDN
connections time out. It stores only stable image files and a public manifest;
the Meta token and temporary signed source URLs are never persisted or logged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen


MAX_IMAGE_BYTES = 12 * 1024 * 1024
CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
}
GRAPH_FIELDS = "id,media_type,thumbnail_url,media_url"


def is_meta_cdn_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == "cdninstagram.com"
        or host.endswith(".cdninstagram.com")
        or host == "fbcdn.net"
        or host.endswith(".fbcdn.net")
    )


class MetaOnlyRedirects(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Request:
        target = urljoin(req.full_url, newurl)
        if not is_meta_cdn_url(target):
            raise URLError("redirect outside Meta CDN")
        return super().redirect_request(req, fp, code, msg, headers, target)


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def graph_media(account_id: str, token: str, version: str, limit: int | None) -> list[dict[str, Any]]:
    params = urlencode({"fields": GRAPH_FIELDS, "limit": "100", "access_token": token})
    next_url = f"https://graph.facebook.com/{version}/{account_id}/media?{params}"
    result: list[dict[str, Any]] = []
    while next_url and (limit is None or len(result) < limit):
        with urlopen(next_url, timeout=30) as response:
            payload = json.load(response)
        for item in payload.get("data", []):
            result.append(item)
            if limit is not None and len(result) >= limit:
                break
        next_url = str((payload.get("paging") or {}).get("next") or "")
    return result


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "covers": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    covers = payload.get("covers")
    if payload.get("schema_version") != 1 or not isinstance(covers, dict):
        raise RuntimeError("invalid existing manifest")
    return payload


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".part")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def download_cover(source_url: str, target_dir: Path, media_id: str) -> tuple[str, str] | None:
    if not is_meta_cdn_url(source_url):
        return None
    opener = build_opener(MetaOnlyRedirects())
    request = Request(source_url, headers={"User-Agent": "MBS Instagram cover mirror/1.0"})
    try:
        with opener.open(request, timeout=45) as response:
            content_type = response.headers.get_content_type().lower()
            extension = CONTENT_TYPES.get(content_type)
            declared_size = response.headers.get("Content-Length")
            if not extension or (declared_size and int(declared_size) > MAX_IMAGE_BYTES):
                return None
            filename = f"{hashlib.sha256(media_id.encode('utf-8')).hexdigest()}.{extension}"
            target = target_dir / filename
            temporary = target.with_suffix(target.suffix + ".part")
            size = 0
            with temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_IMAGE_BYTES:
                        temporary.unlink(missing_ok=True)
                        return None
                    output.write(chunk)
            temporary.replace(target)
            return filename, content_type
    except (HTTPError, OSError, URLError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "recent", "full"), required=True)
    parser.add_argument("--limit", type=int, required=True)
    args = parser.parse_args()
    if args.mode != "full" and args.limit < 1:
        raise SystemExit("--limit must be positive for smoke and recent modes")

    token = required_env("MBS_META_ACCESS_TOKEN")
    account_id = required_env("MBS_META_IG_ACCOUNT_ID")
    version = os.environ.get("MBS_META_API_VERSION", "v23.0").strip() or "v23.0"
    repository = required_env("MBS_MEDIA_REPO")
    root = Path(__file__).resolve().parents[1]
    covers_dir = root / "instagram-covers"
    manifest_path = covers_dir / "manifest.json"
    covers_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(manifest_path)
    entries: dict[str, Any] = manifest["covers"]
    limit = None if args.mode == "full" else args.limit
    media = graph_media(account_id, token, version, limit)

    mirrored = 0
    skipped = 0
    failed = 0
    for item in media:
        media_id = str(item.get("id") or "")
        source_url = str(item.get("thumbnail_url") or item.get("media_url") or "")
        if not media_id or media_id in entries:
            skipped += 1
            continue
        downloaded = download_cover(source_url, covers_dir, media_id)
        if not downloaded:
            failed += 1
            continue
        filename, content_type = downloaded
        entries[media_id] = {
            "content_type": content_type,
            "url": f"https://raw.githubusercontent.com/{repository}/main/instagram-covers/{filename}",
        }
        mirrored += 1

    manifest["generated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    atomic_json_write(manifest_path, manifest)
    print(json.dumps({"listed": len(media), "mirrored": mirrored, "skipped": skipped, "failed": failed}))
    if args.mode == "smoke" and not mirrored:
        raise SystemExit("smoke run did not mirror a cover")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
