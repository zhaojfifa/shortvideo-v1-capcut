import boto3
import mimetypes
import os
from gateway.app.ports.storage import IStorageService
from gateway.app.utils.keys import KeyBuilder

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
            aws_secret_access_key=aws_secret_access_key
        )

    def upload_file(
        self,
        file_path: str,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        if not content_type:
            guess, _ = mimetypes.guess_type(file_path)
            content_type = guess or "application/octet-stream"
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

    def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        return self.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket_name, 'Key': key},
            ExpiresIn=expiration
        )
