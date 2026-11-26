import os
from pathlib import Path
from dotenv import load_dotenv

# landlease/app/core/config.py -> 上级三级为项目根
ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / '.env', override=False)


def _env(k: str, default: str = '') -> str:
    return os.getenv(k, default)


class Settings:
    PROJECT_ROOT: Path = ROOT
    STORAGE_DIR: Path = ROOT / 'storage'

    DB_HOST: str = _env('DB_HOST', '127.0.0.1')
    DB_PORT: int = int(_env('DB_PORT', '3306'))
    DB_USER: str = _env('DB_USER', 'root')
    DB_PASSWORD: str = _env('DB_PASSWORD', '')
    DB_NAME: str = _env('DB_NAME', 'landlease')

    DASHSCOPE_API_KEY: str = _env('DASHSCOPE_API_KEY', '')
    DASHSCOPE_BASE_URL: str = _env('DASHSCOPE_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
    DEFAULT_VL_MODEL: str = _env('DEFAULT_VL_MODEL', 'qwen3-vl-plus')

    # 开源通道（权重开源、可本地部署；比赛阶段经云端 OpenAI 兼容接口调用，不要求自备显卡）
    # 默认接硅基流动 SiliconFlow 托管的 Qwen3-VL-32B-Instruct；正式环境改为政务网内 vLLM 地址即可
    OPENSOURCE_BASE_URL: str = _env('OPENSOURCE_BASE_URL', 'https://api.siliconflow.cn/v1')
    OPENSOURCE_API_KEY: str = _env('OPENSOURCE_API_KEY', '')
    OPENSOURCE_VL_MODEL: str = _env('OPENSOURCE_VL_MODEL', 'Qwen/Qwen3-VL-32B-Instruct')

    # 判定阈值（配置中心可覆盖）
    AUTO_PASS_CONFIDENCE: float = float(_env('AUTO_PASS_CONFIDENCE', '0.90'))
    CALC_RULE_VERSION: str = _env('CALC_RULE_VERSION', 'v1.2')

    # 直连串覆盖：设置后忽略上面 5 个 DB_* 项。
    # 用于 SQLite 演示包（DB_URL=sqlite:///./demo.db），正式部署仍走 MySQL 默认拼装。
    DB_URL: str = _env('DB_URL', '')

    @property
    def db_url(self) -> str:
        if self.DB_URL:
            return self.DB_URL
        return (f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4")


settings = Settings()
