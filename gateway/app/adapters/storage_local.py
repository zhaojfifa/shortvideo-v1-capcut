import os
import shutil
from gateway.app.ports.storage import IStorageService

class LocalStorageService(IStorageService):
    def __init__(self, root_dir: str):
        """
        初始化本地存储服务
        :param root_dir: 本地存储的根目录 (例如 ./data_debug)
        """
        self.root_dir = root_dir
        # 确保根目录存在
        os.makedirs(self.root_dir, exist_ok=True)

    def upload_file(
        self,
        local_path: str,
        remote_key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        # 拼接完整的目标路径
        dest_path = os.path.join(self.root_dir, remote_key)
        
        # 确保目标文件夹存在
        directory = os.path.dirname(dest_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        
        # 复制文件
        shutil.copy2(local_path, dest_path)
        
        # 返回一个本地文件协议路径
        return f"file://{os.path.abspath(dest_path)}"

    def download_file(self, remote_key: str, local_path: str):
        src_path = os.path.join(self.root_dir, remote_key)
        
        if not os.path.exists(src_path):
            raise FileNotFoundError(f"Local file not found: {src_path}")
            
        # === 核心修复点 ===
        # 获取目标文件夹路径
        directory = os.path.dirname(local_path)
        # 只有当 directory 不为空（即不是当前目录）时，才创建文件夹
        if directory:
            os.makedirs(directory, exist_ok=True)
        # =================
        
        shutil.copy2(src_path, local_path)

    def exists(self, remote_key: str) -> bool:
        path = os.path.join(self.root_dir, remote_key)
        return os.path.exists(path)

    def generate_presigned_url(
        self,
        remote_key: str,
        expiration=3600,
        content_type: str | None = None,
        filename: str | None = None,
        disposition: str | None = None,
    ) -> str:
        # 本地模拟返回 web 路径
        return f"/files/{remote_key}"
