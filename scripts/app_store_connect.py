#!/usr/bin/env python3
"""Adapted from Visio-Vanitas/Bugaoshan apple-ci .github/scripts/app_store_connect.py."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.appstoreconnect.apple.com"


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def read_der_length(data: bytes, offset: int) -> tuple[int, int]:
    first = data[offset]
    if first < 0x80:
        return first, offset + 1
    byte_count = first & 0x7F
    start = offset + 1
    return int.from_bytes(data[start : start + byte_count], "big"), start + byte_count


def der_signature_to_raw(signature: bytes) -> bytes:
    if not signature or signature[0] != 0x30:
        raise RuntimeError("invalid ECDSA DER signature")
    _, offset = read_der_length(signature, 1)
    if signature[offset] != 0x02:
        raise RuntimeError("invalid ECDSA r component")
    r_length, offset = read_der_length(signature, offset + 1)
    r = signature[offset : offset + r_length]
    offset += r_length
    if signature[offset] != 0x02:
        raise RuntimeError("invalid ECDSA s component")
    s_length, offset = read_der_length(signature, offset + 1)
    s = signature[offset : offset + s_length]
    return r.lstrip(b"\0").rjust(32, b"\0") + s.lstrip(b"\0").rjust(32, b"\0")


def make_token(key_path: Path, key_id: str, issuer_id: str) -> str:
    issued_at = int(time.time())
    header = base64url(
        json.dumps(
            {"alg": "ES256", "kid": key_id, "typ": "JWT"}, separators=(",", ":")
        ).encode()
    )
    payload = base64url(
        json.dumps(
            {
                "iss": issuer_id,
                "iat": issued_at,
                "exp": issued_at + 10 * 60,
                "aud": "appstoreconnect-v1",
            },
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    der_signature = subprocess.check_output(
        ["openssl", "dgst", "-sha256", "-sign", str(key_path)],
        input=signing_input,
    )
    return f"{header}.{payload}.{base64url(der_signature_to_raw(der_signature))}"


class AppStoreConnectClient:
    def __init__(self, key_path: Path, key_id: str, issuer_id: str) -> None:
        self.key_path = key_path
        self.key_id = key_id
        self.issuer_id = issuer_id

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        allowed_statuses: tuple[int, ...] = (),
    ) -> dict[str, Any] | None:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"{API_URL}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {make_token(self.key_path, self.key_id, self.issuer_id)}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as error:
            if error.code in allowed_statuses:
                return None
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"App Store Connect {method} {path}: {error.code} {detail}") from error

    def get(self, path: str) -> dict[str, Any]:
        response = self.request("GET", path)
        if response is None:
            raise RuntimeError(f"empty response from {path}")
        return response


def find_app(client: AppStoreConnectClient, bundle_id: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"filter[bundleId]": bundle_id, "limit": 2})
    apps = client.get(f"/v1/apps?{query}")["data"]
    if len(apps) != 1:
        raise RuntimeError(f"expected one app for {bundle_id}, found {len(apps)}")
    return apps[0]


def list_groups(
    client: AppStoreConnectClient, bundle_id: str
) -> list[dict[str, Any]]:
    app = find_app(client, bundle_id)
    query = urllib.parse.urlencode(
        {
            "fields[betaGroups]": "name,isInternalGroup,hasAccessToAllBuilds",
            "limit": 200,
        }
    )
    return client.get(f"/v1/apps/{app['id']}/betaGroups?{query}")["data"]


def wait_for_build(
    client: AppStoreConnectClient,
    app_id: str,
    marketing_version: str,
    build_number: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        build = find_build(
            client, app_id, marketing_version, build_number, allow_missing=True
        )
        if build:
            state = build["attributes"]["processingState"]
            print(f"TestFlight build processing state: {state}", flush=True)
            if state == "VALID":
                return build
            if state in {"FAILED", "INVALID"}:
                raise RuntimeError(f"TestFlight processing ended in {state}")
        else:
            print("Waiting for uploaded build to appear in App Store Connect", flush=True)
        time.sleep(30)
    raise TimeoutError("timed out waiting for TestFlight build processing")


def find_build(
    client: AppStoreConnectClient,
    app_id: str,
    marketing_version: str,
    build_number: str,
    allow_missing: bool,
) -> dict[str, Any] | None:
    query = urllib.parse.urlencode(
        {
            "filter[app]": app_id,
            "filter[version]": build_number,
            "filter[preReleaseVersion.version]": marketing_version,
            "limit": 2,
        }
    )
    builds = client.get(f"/v1/builds?{query}")["data"]
    if len(builds) > 1:
        raise RuntimeError(f"multiple builds found for {marketing_version} ({build_number})")
    if builds:
        return builds[0]
    if allow_missing:
        return None
    raise RuntimeError(f"build {marketing_version} ({build_number}) was not found")


def add_build_to_group(
    client: AppStoreConnectClient, group_id: str, build_id: str
) -> None:
    client.request(
        "POST",
        f"/v1/betaGroups/{group_id}/relationships/builds",
        {"data": [{"type": "builds", "id": build_id}]},
        allowed_statuses=(409,),
    )


def submit_beta_review(client: AppStoreConnectClient, build_id: str) -> None:
    existing = client.request(
        "GET",
        f"/v1/builds/{build_id}/betaAppReviewSubmission",
        allowed_statuses=(404,),
    )
    if existing and existing.get("data"):
        state = existing["data"]["attributes"]["betaReviewState"]
        if state in {"WAITING_FOR_REVIEW", "IN_REVIEW", "APPROVED"}:
            print(f"Beta App Review already {state}")
            return
        raise RuntimeError(f"existing Beta App Review is {state}")
    client.request("POST", "/v1/betaAppReviewSubmissions", {
        "data": {"type": "betaAppReviewSubmissions", "relationships": {
            "build": {"data": {"type": "builds", "id": build_id}}
        }}
    })
    print("Submitted build for Beta App Review; approval is still pending")


def _strip_emoji(text: str) -> str:
    import re
    return re.sub(
        r"[\U00002190-\U000021FF"
        r"\U00002300-\U000023FF"
        r"\U00002600-\U000027BF"
        r"\U00002900-\U00002BFF"
        r"\U0000FE00-\U0000FE0F"
        r"\U0001F000-\U0001FBFF"
        r"\U0000200D"
        r"\U000020E3"
        r"\U00003299\U00003297]+",
        "",
        text,
    )


def set_whats_new(client: AppStoreConnectClient, build_id: str, whats_new: str) -> None:
    if not whats_new:
        return
    # App Store Connect rejects emoji in whatsNew text
    whats_new = _strip_emoji(whats_new)
    # App Store Connect has a 4000 character limit for whatsNew
    whats_new = whats_new[:3900]
    response = client.get(f"/v1/builds/{build_id}/betaBuildLocalizations")
    localizations = response.get("data", [])
    target_locales = ["zh-Hans", "en-US"]

    for locale in target_locales:
        existing = next((loc for loc in localizations if loc["attributes"]["locale"] == locale), None)
        if existing:
            loc_id = existing["id"]
            client.request(
                "PATCH",
                f"/v1/betaBuildLocalizations/{loc_id}",
                {
                    "data": {
                        "type": "betaBuildLocalizations",
                        "id": loc_id,
                        "attributes": {
                            "whatsNew": whats_new
                        }
                    }
                }
            )
            print(f"Updated TestFlight What's New for {locale}", flush=True)
        else:
            client.request(
                "POST",
                "/v1/betaBuildLocalizations",
                {
                    "data": {
                        "type": "betaBuildLocalizations",
                        "attributes": {
                            "whatsNew": whats_new,
                            "locale": locale
                        },
                        "relationships": {
                            "build": {
                                "data": {
                                    "type": "builds",
                                    "id": build_id
                                }
                            }
                        }
                    }
                }
            )
            print(f"Created TestFlight What's New for {locale}", flush=True)


def publish_testflight(
    client: AppStoreConnectClient,
    bundle_id: str,
    marketing_version: str,
    build_number: str,
    group_ids: list[str],
    timeout_seconds: int,
    whats_new: str = "",
) -> None:
    if not group_ids:
        raise RuntimeError("at least one TestFlight beta group ID is required")
    app = find_app(client, bundle_id)
    groups = {group["id"]: group for group in list_groups(client, bundle_id)}
    unknown_group_ids = sorted(set(group_ids) - groups.keys())
    if unknown_group_ids:
        raise RuntimeError(f"beta groups do not belong to this app: {unknown_group_ids}")

    build = wait_for_build(
        client, app["id"], marketing_version, build_number, timeout_seconds
    )

    set_whats_new(client, build["id"], whats_new)

    for group_id in group_ids:
        group = groups[group_id]
        if group["attributes"]["isInternalGroup"]:
            print(f"Group {group['attributes']['name']} is internal; skipping explicit assignment.", flush=True)
            continue
        add_build_to_group(client, group_id, build["id"])
        print(f"Added build to TestFlight group {group['attributes']['name']}")

    if any(not groups[group_id]["attributes"]["isInternalGroup"] for group_id in group_ids):
        submit_beta_review(client, build["id"])
    else:
        print("All selected groups are internal; Beta App Review is not required")


def make_client(args: argparse.Namespace) -> AppStoreConnectClient:
    return AppStoreConnectClient(args.key, args.key_id, args.issuer_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--issuer-id", required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    groups_parser = subparsers.add_parser("groups")
    groups_parser.add_argument("--bundle-id", required=True)

    exists_parser = subparsers.add_parser("exists")
    exists_parser.add_argument("--bundle-id", required=True)
    exists_parser.add_argument("--version", required=True)
    exists_parser.add_argument("--build-number", required=True)

    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("--bundle-id", required=True)
    publish_parser.add_argument("--version", required=True)
    publish_parser.add_argument("--build-number", required=True)
    publish_parser.add_argument("--group-ids", required=True)
    publish_parser.add_argument("--timeout", type=int, default=2700)
    publish_parser.add_argument("--whats-new-file", type=Path)
    args = parser.parse_args()

    if args.command == "groups":
        groups = list_groups(make_client(args), args.bundle_id)
        print(
            json.dumps(
                [
                    {
                        "id": group["id"],
                        "name": group["attributes"]["name"],
                        "internal": group["attributes"]["isInternalGroup"],
                        "all_builds": group["attributes"]["hasAccessToAllBuilds"],
                    }
                    for group in groups
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    if args.command == "exists":
        client = make_client(args)
        app = find_app(client, args.bundle_id)
        build = find_build(
            client,
            app["id"],
            args.version,
            args.build_number,
            allow_missing=True,
        )
        if build is None:
            raise SystemExit(1)
        print(build["attributes"]["processingState"])
        return

    group_ids = [value.strip() for value in args.group_ids.split(",") if value.strip()]
    whats_new = ""
    if args.whats_new_file and args.whats_new_file.exists():
        whats_new = args.whats_new_file.read_text(encoding="utf-8")
    publish_testflight(
        make_client(args),
        args.bundle_id,
        args.version,
        args.build_number,
        group_ids,
        args.timeout,
        whats_new=whats_new,
    )


if __name__ == "__main__":
    main()
