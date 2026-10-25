"""Download a manifest-bound model from an S3 prefix into an atomic local cache."""

import hashlib
import json
import tempfile
from pathlib import Path, PurePosixPath

from app.core.config import Settings


def resolve_s3_model(settings: Settings) -> Path:
    import boto3
    from boto3.s3.transfer import TransferConfig

    cache = settings.hf_cache_dir.resolve() / "s3-packages"
    cache.mkdir(parents=True, exist_ok=True)
    identity = (
        f"{settings.s3_endpoint_url}/{settings.s3_bucket}/{settings.s3_prefix}@{settings.model_revision}"
    )
    target = cache / hashlib.sha256(identity.encode()).hexdigest()
    if not target.resolve().is_relative_to(cache):
        raise ValueError("Unsafe S3 cache path")
    if target.is_dir():
        return target
    kwargs = {
        "endpoint_url": settings.s3_endpoint_url,
        "region_name": settings.aws_default_region,
        "aws_access_key_id": settings.aws_access_key_id.get_secret_value()
        if settings.aws_access_key_id
        else None,
        "aws_secret_access_key": settings.aws_secret_access_key.get_secret_value()
        if settings.aws_secret_access_key
        else None,
        "aws_session_token": settings.aws_session_token.get_secret_value()
        if settings.aws_session_token
        else None,
    }
    manifest_name = "finetune-manifest.json" if settings.model_variant == "finetuned" else "manifest.json"

    def key(name):
        return settings.s3_prefix.rstrip("/") + "/" + name if settings.s3_prefix else name

    try:
        client = boto3.client("s3", **{k: v for k, v in kwargs.items() if v is not None})
        response = client.get_object(Bucket=settings.s3_bucket, Key=key(manifest_name))
        with response["Body"] as body:
            raw = body.read(1048577)
        if len(raw) > 1048576:
            raise ValueError("Manifest too large")
        manifest = json.loads(raw)
        files = manifest["checksums"]
        if not isinstance(files, dict) or not 1 <= len(files) <= 50:
            raise ValueError("Invalid file list")
        if settings.model_variant == "finetuned":
            fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
            if (
                manifest["artifactSha256"] != settings.model_revision
                or fingerprint != settings.model_revision
            ):
                raise ValueError("Wrong artifact")
        elif manifest["revision"] != settings.model_revision or manifest["modelId"] != settings.model_id:
            raise ValueError("Wrong base model")
        for name in files:
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or ":" in name
                or path.suffix in (".bin", ".pkl", ".pickle", ".py")
            ):
                raise ValueError("Unsafe model file")
        with tempfile.TemporaryDirectory(prefix=".s3-", dir=cache) as temporary:
            stage = Path(temporary) / "model"
            stage.mkdir()
            (stage / manifest_name).write_bytes(raw)
            transfer = TransferConfig(max_concurrency=2, multipart_chunksize=8 * 1024 * 1024)
            for name, expected in files.items():
                destination = stage / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                client.download_file(settings.s3_bucket, key(name), str(destination), Config=transfer)
                with destination.open("rb") as source:
                    if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                        raise ValueError("Checksum mismatch")
            try:
                stage.rename(target)
            except OSError:
                if not target.is_dir():
                    raise
    except Exception:
        raise ValueError("S3 model download failed; check bucket access, prefix and manifest") from None
    return target
