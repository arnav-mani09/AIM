"""Pinned HTTPS transport shared with the isolated Modal import worker."""

import http.client
import ipaddress
import re
import socket
import ssl
import time
from pathlib import Path
from urllib.parse import parse_qsl, urljoin, urlsplit

MAX_BYTES = 5 * 1024**3
PART_BYTES = 64 * 1024**2
MAX_SECONDS = 2 * 60 * 60
REDIRECTS = {301, 302, 303, 307, 308}
VIDEO_TYPES = {"video/mp4", "video/quicktime"}
BRANDS = {b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"M4V ", b"qt  "}


class ImportRejected(ValueError):
    pass


def validate_source_url(source_url: str, allowed_hosts: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(source_url)
        host = (parsed.hostname or "").lower()
        allowed = {value.strip().lower() for value in allowed_hosts.split(",") if value.strip()}
        if (
            parsed.scheme != "https" or not host or host not in allowed
            or parsed.username is not None or parsed.password is not None
            or parsed.port not in (None, 443) or parsed.fragment
            or "\\" in source_url or any(ord(char) <= 32 or ord(char) >= 127 for char in source_url)
        ):
            raise ValueError
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError
        return host, parsed.path or "/"
    except (ValueError, UnicodeError):
        raise ImportRejected("Use an authorized HTTPS direct video download from an enabled provider.") from None


def normalize_source_url(source_url: str, allowed_hosts: str) -> str:
    try:
        parsed = urlsplit(source_url)
        if (parsed.hostname or "").lower() == "www.hudl.com":
            validate_source_url(source_url, "www.hudl.com")
            if not re.fullmatch(
                r"/notifications-tracking/tracker/BulkDownloadReady-[A-Za-z0-9-]+/email/landing",
                parsed.path,
            ):
                raise ValueError
            parameters = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
            if len(parameters) != 1 or parameters[0][0] != "forward":
                raise ValueError
            source_url = parameters[0][1]
            target = urlsplit(source_url)
            if (target.hostname or "").lower() != "vtemp.hudl.com" or not target.path.lower().endswith((".mp4", ".mov")):
                raise ValueError
        validate_source_url(source_url, allowed_hosts)
        return source_url
    except (ValueError, UnicodeError):
        raise ImportRejected(
            "Use an authorized direct MP4/MOV download or a Hudl video download-email link from an enabled provider. "
            "Hudl watch pages and stats links cannot import film."
        ) from None


def resolve_public(host: str) -> list[tuple]:
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        def unsafe(address):
            value = ipaddress.ip_address(address[4][0])
            return (
                not value.is_global or value.is_reserved or value.is_multicast
                or value.is_loopback or value.is_link_local or value.is_unspecified
                or getattr(value, "is_site_local", False)
                or (value.version == 4 and any(value in network for network in (
                    ipaddress.ip_network("192.0.0.0/24"), ipaddress.ip_network("192.88.99.0/24"),
                )))
                or getattr(value, "ipv4_mapped", None) is not None
                or getattr(value, "sixtofour", None) is not None
                or getattr(value, "teredo", None) is not None
            )

        if not addresses or any(unsafe(address) for address in addresses):
            raise ValueError
        return addresses
    except (OSError, ValueError):
        raise ImportRejected("The download host must resolve only to public addresses.") from None


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: tuple):
        super().__init__(host, timeout=30, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        family, kind, protocol, _, endpoint = self.address
        connection = socket.socket(family, kind, protocol)
        try:
            connection.settimeout(self.timeout)
            connection.connect(endpoint)
            self.sock = self._context.wrap_socket(connection, server_hostname=self.host)
        except BaseException:
            connection.close()
            raise


def open_download(source_url: str, allowed_hosts: str):
    current = source_url
    for _ in range(6):
        host, _ = validate_source_url(current, allowed_hosts)
        addresses = resolve_public(host)
        connection = PinnedHTTPSConnection(host, addresses[0])
        response = None
        try:
            parsed = urlsplit(current)
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            connection.request("GET", target, headers={"Accept-Encoding": "identity", "Accept": "video/mp4, video/quicktime"})
            response = connection.getresponse()
            if response.status in REDIRECTS:
                location = response.getheader("Location")
                if not location:
                    raise ImportRejected("The provider returned an invalid redirect.")
                current = urljoin(current, location)
                response.close()
                connection.close()
                continue
            if response.status != 200:
                raise ImportRejected("The direct download is unavailable or expired. Obtain a new authorized link.")
            return connection, response
        except BaseException:
            if response:
                response.close()
            connection.close()
            raise
    raise ImportRejected("The download redirected too many times.")


def import_to_r2(source_url: str, allowed_hosts: str, client, bucket: str, key: str, local_path: Path, probe) -> dict:
    connection = None
    response = None
    multipart_id = None
    completed = False
    started = time.monotonic()
    try:
        connection, response = open_download(source_url, allowed_hosts)
        content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type not in VIDEO_TYPES or response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise ImportRejected("The link must download an MP4 or MOV video, not a watch page.")
        declared = response.getheader("Content-Length")
        if declared is not None and (not declared.isdecimal() or not 0 < int(declared) <= MAX_BYTES):
            raise ImportRejected("Film must be nonempty and 5 GB or smaller.")
        multipart_id = client.create_multipart_upload(Bucket=bucket, Key=key, ContentType=content_type)["UploadId"]
        parts = []
        total = 0
        with local_path.open("wb") as destination:
            while True:
                part = bytearray()
                while len(part) < PART_BYTES:
                    if time.monotonic() - started > MAX_SECONDS:
                        raise ImportRejected("The download exceeded the two-hour import limit.")
                    chunk = response.read(min(1024**2, PART_BYTES - len(part), MAX_BYTES - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise ImportRejected("Film must be 5 GB or smaller.")
                    part.extend(chunk)
                if not part:
                    break
                if not parts and (len(part) < 12 or part[4:8] != b"ftyp" or bytes(part[8:12]) not in BRANDS):
                    raise ImportRejected("The download is not a supported MP4 or MOV container.")
                destination.write(part)
                number = len(parts) + 1
                uploaded = client.upload_part(Bucket=bucket, Key=key, UploadId=multipart_id, PartNumber=number, Body=bytes(part))
                parts.append({"PartNumber": number, "ETag": uploaded["ETag"]})
        if not total or (declared is not None and total != int(declared)):
            raise ImportRejected("The video download was empty or incomplete.")
        info = probe(local_path)
        if not info.get("width") or not info.get("height") or info.get("duration", 0) <= 0:
            raise ImportRejected("The download does not contain a playable video stream.")
        client.complete_multipart_upload(Bucket=bucket, Key=key, UploadId=multipart_id, MultipartUpload={"Parts": parts})
        completed = True
        return {"source_key": key, "size_bytes": total}
    finally:
        if response:
            response.close()
        if connection:
            connection.close()
        if multipart_id and not completed:
            try:
                client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=multipart_id)
            except Exception:
                pass
