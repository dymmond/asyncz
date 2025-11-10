from dataclasses import dataclass

from asyncz.conf.global_settings import Settings as BaseSettings
from asyncz.contrib.dashboard.config import DashboardConfig


@dataclass
class DevConfig(DashboardConfig):
    secret_key: str = "development"
    session_cookie: str = "dec_asyncz_admin"


class Settings(BaseSettings):
    @property
    def dashboard_config(self) -> DevConfig:
        return DevConfig()
