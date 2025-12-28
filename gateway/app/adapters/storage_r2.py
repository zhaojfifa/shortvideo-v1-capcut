import boto3
import mimetypes
from gateway.adapters.r2_s3_client import get_s3_client
from gateway.app.ports.storage import IStorageService

class R2StorageService(IStorageService):
    def __init__(
        self,
        bucket_name: str,
        endpoint_url: str,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        **kwargs,
    ):
        if aws_access_key_id is None and access_key_id:
            aws_access_key_id = access_key_id
        if aws_secret_access_key is None and secret_access_key:
            aws_secret_access_key = secret_access_key
        if aws_access_key_id is None and access_key:
            aws_access_key_id = access_key
        if aws_secret_access_key is None and secret_key:
            aws_secret_access_key = secret_key
        self.bucket_name = bucket_name
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        self._presign_client = get_s3_client()

    def upload_file(
        self,
        file_path: str,
        key: str,
        content_type: str | None = None,
    ) -> str:
        if not content_type:
            guess, _ = mimetypes.guess_type(file_path)
            content_type = guess
            if not content_type:
                lower_path = str(file_path).lower()
                if lower_path.endswith(".mp3"):
                    content_type = "audio/mpeg"
                elif lower_path.endswith(".zip"):
                    content_type = "application/zip"
                elif lower_path.endswith(".srt"):
                    content_type = "text/plain; charset=utf-8"
                elif lower_path.endswith(".txt"):
                    content_type = "text/plain; charset=utf-8"
                else:
                    content_type = "application/octet-stream"
        self.s3_client.upload_file(
            file_path,
            self.bucket_name,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return key

    def download_file(self, key: str, destination_path: str) -> None:
        self.s3_client.download_file(self.bucket_name, key, destination_path)

    def exists(self, key: str) -> bool:
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except self.s3_client.exceptions.ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                raise

    def generate_presigned_url(
        self,
        key: str,
        expiration: int = 3600,
        content_type: str | None = None,
        filename: str | None = None,
        disposition: str | None = None,
    ) -> str:
        params = {"Bucket": self.bucket_name, "Key": key}
        if content_type:
            params["ResponseContentType"] = content_type
        else:
            key_lower = key.lower()
            if key_lower.endswith(".zip"):
                params["ResponseContentType"] = "application/zip"
            elif key_lower.endswith(".mp3"):
                params["ResponseContentType"] = "audio/mpeg"
            elif key_lower.endswith(".srt") or key_lower.endswith(".txt"):
                params["ResponseContentType"] = "text/plain; charset=utf-8"
        if filename:
            disp = disposition or "attachment"
            params["ResponseContentDisposition"] = f'{disp}; filename="{filename}"'
        elif disposition:
            params["ResponseContentDisposition"] = disposition
        return self._presign_client.generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=expiration
        )
