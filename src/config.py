"""
配置加载模块 - 负责加载和验证模板配置
"""

import yaml
import os
from pathlib import Path
from datetime import datetime


class TemplateConfig:
    """模板配置类"""

    def __init__(self, template_name: str):
        self.template_name = template_name
        self.config_path = Path(f"templates/{template_name}/config.yaml")
        self.config = self._load_config()
        self._validate_config()

    def _load_config(self) -> dict:
        """加载 YAML 配置文件"""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"模板配置文件不存在: {self.config_path}\n"
                f"可用模板: {self.list_available_templates()}"
            )

        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _validate_config(self):
        """验证配置文件完整性"""
        required_keys = ["border", "bgm", "transitions", "font", "subtitle"]
        missing = [key for key in required_keys if key not in self.config]
        if missing:
            raise ValueError(f"配置文件缺少必要字段: {missing}")

        # 验证文件路径
        border_path = self.config["border"]["path"]
        if not os.path.exists(border_path):
            print(f"⚠️  警告: 边框文件不存在: {border_path}")

        bgm_path = self.config["bgm"]["path"]
        if not os.path.exists(bgm_path):
            print(f"⚠️  警告: BGM 文件不存在: {bgm_path}")

        font_path = self.config["font"]["path"]
        if not os.path.exists(font_path):
            raise FileNotFoundError(f"字体文件不存在: {font_path}")

    @staticmethod
    def list_available_templates() -> list:
        """列出所有可用模板"""
        templates_dir = Path("templates")
        if not templates_dir.exists():
            return []
        return [
            d.name
            for d in templates_dir.iterdir()
            if d.is_dir() and (d / "config.yaml").exists()
        ]

    def get_subtitle_text(self) -> str:
        """生成字幕文本（带日期）"""
        now = datetime.now()
        template = self.config["subtitle"]["template"]
        return template.format(year=now.year, month=now.month, day=now.day)

    def __getattr__(self, name):
        """便捷访问配置项"""
        if name in self.config:
            return self.config[name]
        raise AttributeError(f"配置项 '{name}' 不存在")

    def __repr__(self):
        return f"TemplateConfig('{self.template_name}')"
