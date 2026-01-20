import configparser
import os
from utils import user_data_path

class ConfigHandler:
    def __init__(self, config_file='config.conf'):
        self.config_file = user_data_path(config_file)
        self.config = configparser.ConfigParser()
        self._load_config()

    def _create_default_config(self):
        """创建或覆盖为默认配置文件"""
        self.config['SERIAL'] = {'COM': 'COM5'}
        self.config['AI'] = {'platform': 'deepseek'}
        
        # Platform Configs
        self.config['deepseek'] = {
            "api_key": "sk-xxxxxxxxxxxxxxxx",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat"
        }
        self.config['volcengine'] = {
            "api_key": "xxxxxxxxxxxxxxxx",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "model": "ep-xxxxxxxxxxxxxx-xxxxx"
        }
        self.config['aliyun'] = {
            "api_key": "sk-xxxxxxxxxxxxxxxx",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-plus"
        }
        self.config['openai'] = {
            "api_key": "sk-xxxxxxxxxxxxxxxx",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4-1106-preview"
        }

        with open(self.config_file, 'w') as f:
            self.config.write(f)
        print(f"已创建/重置为默认配置: {self.config_file}")

    def _load_config(self):
        """加载或创建配置文件"""
        if not os.path.exists(self.config_file):
            self._create_default_config()
        else:
            try:
                read_ok = self.config.read(self.config_file, encoding='utf-8')
                if not read_ok:
                    raise ValueError("配置文件为空。")
                
                # 检查并补充缺失的配置项
                updated = False
                
                if 'SERIAL' not in self.config:
                    self.config['SERIAL'] = {'COM': 'COM5'}
                    updated = True
                
                if 'AI' not in self.config:
                    self.config['AI'] = {'platform': 'deepseek'}
                    updated = True
                
                # Check for platform configs
                platforms = ['deepseek', 'volcengine', 'aliyun', 'openai']
                for p in platforms:
                    section = p
                    if section not in self.config:
                        if p == 'deepseek':
                            self.config[section] = {"api_key": "sk-xxxxxxxxxxxxxxxx", "base_url": "https://api.deepseek.com", "model": "deepseek-chat"}
                        elif p == 'volcengine':
                            self.config[section] = {"api_key": "xxxxxxxxxxxxxxxx", "base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": "ep-20251224114653-z55vt"}
                        elif p == 'aliyun':
                            self.config[section] = {"api_key": "sk-xxxxxxxxxxxxxxxx", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"}
                        elif p == 'openai':
                            self.config[section] = {"api_key": "sk-xxxxxxxxxxxxxxxx", "base_url": "https://api.openai.com/v1", "model": "gpt-4-1106-preview"}
                        updated = True
                
                if updated:
                    with open(self.config_file, 'w') as f:
                        self.config.write(f)
                    print(f"已更新配置文件: {self.config_file}")
                else:
                    print(f"已加载配置: {self.config_file}")

            except (configparser.Error, ValueError) as e:
                print(f"配置文件 '{self.config_file}' 格式错误或不完整: {e}。将使用默认配置重建。")
                self._create_default_config()

    def get_com_port(self) -> str:
        """获取 COM 端口号"""
        try:
            # ConfigParser 会将 option 名称转为小写
            return self.config.get('SERIAL', 'com').strip("'\"")
        except (configparser.NoSectionError, configparser.NoOptionError):
            # 如果配置丢失，返回默认值并重新生成配置
            self._create_default_config()
            return self.config.get('SERIAL', 'com').strip("'\"")
    
    def get_time_sync_interval(self) -> int:
        """获取时间同步间隔（分钟），默认10分钟"""
        default_value = 10
        try:
            # 检查配置项是否存在
            if not self.config.has_option('SERIAL', 'time_sync_interval'):
                # 不存在则设置默认值并保存
                self.config.set('SERIAL', 'time_sync_interval', str(default_value))
                with open(self.config_file, 'w') as f:
                    self.config.write(f)
                print(f"已添加默认配置 time_sync_interval = {default_value}")
                return default_value
            return self.config.getint('SERIAL', 'time_sync_interval')
        except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
            return default_value


    def get_ai_platform(self) -> str:
        """获取当前 AI 平台"""
        try:
            return self.config.get('AI', 'platform').strip("'\"").lower()
        except (configparser.NoSectionError, configparser.NoOptionError):
            return "deepseek"

    def get_platform_config(self, platform_name: str) -> dict:
        """获取指定平台的配置信息"""
        section = platform_name
        if self.config.has_section(section):
            return {
                "api_key": self.config.get(section, "api_key"),
                "base_url": self.config.get(section, "base_url"),
                "model": self.config.get(section, "model")
            }
        return None
