"""Configuration.
@Project   : genshinhelper
@Author    : y1ndan
@Blog      : https://www.yindan.me
@GitHub    : https://github.com/y1ndan
"""

import json
import os

CONFIG_DICT = {
    'LANGUAGE': 'LANGUAGE',
    'RANDOM_SLEEP_SECS_RANGE': 'RANDOM_SLEEP_SECS_RANGE',
    'CHECK_IN_TIME': 'CHECK_IN_TIME',
    'CHECK_RESIN_SECS': 'CHECK_RESIN_SECS',
    'CHECK_RESIN_SECS_RANGE': 'CHECK_RESIN_SECS_RANGE',
    'RESIN_THRESHOLD': 'RESIN_THRESHOLD',
    'RESIN_TIMER_DO_NOT_DISTURB': 'RESIN_TIMER_DO_NOT_DISTURB',
    'GENSHINPY': 'GENSHINPY',
    'GENSHINPY_HONKAI': 'GENSHINPY_HONKAI',
    'GENSHINPY_STARRAIL': 'GENSHINPY_STARRAIL',
    'COOKIE_MIHOYOBBS': 'COOKIE_MIHOYOBBS',
    'COOKIE_RESIN_TIMER': 'COOKIE_RESIN_TIMER',
    'COOKIE_BH3': 'COOKIE_BH3',
    'COOKIE_MIYOUBI': 'COOKIE_MIYOUBI',
    'CLOUD_GENSHIN': 'CLOUD_GENSHIN',
    'COOKIE_HOYOLAB': 'COOKIE_HOYOLAB',
    'COOKIE_WEIBO': 'COOKIE_WEIBO',
    'COOKIE_KA': 'COOKIE_KA',
    'SHOPTOKEN': 'SHOPTOKEN',
    'ONEPUSH': 'ONEPUSH'
}


class Config(object):
    """
    Get all configuration from the config.json file.
    If config.json dose not exist, use config.example.json file.

        Note:   Environment variables have a higher priority,
                if you set a environment variable in your system,
                that variable in the config.json file will be invalid.
    """

    def __init__(self):
        # Open and read the config file
        # project_path = os.path.dirname(os.path.dirname(__file__))
        project_path = os.path.dirname(__file__)
        config_file = os.path.join(project_path, 'config', 'config.json')
        if not os.path.exists(config_file):
            config_file = os.path.join(project_path, 'config', 'config.example.json')

        with open(config_file, 'r', encoding='utf-8') as f:
            self.config_json = json.load(f)

        for i in CONFIG_DICT:
            self.__dict__[i] = self.get_config(i)

    def get_config(self, key: str):
        value = os.environ[key] if os.environ.get(key) else self.config_json.get(key, '')

        default_config_dict = {
            'LANGUAGE': 'en',
            'RANDOM_SLEEP_SECS_RANGE': '0-300',
            'CHECK_IN_TIME': '06:00',
            'CHECK_RESIN_SECS': 900,
            'RESIN_THRESHOLD': 150,
            'RESIN_TIMER_DO_NOT_DISTURB': '23:00-07:00'
        }

        for k, v in default_config_dict.items():
            if key == k and not value:
                value = v

        if (key == 'ONEPUSH' or
            key == 'GENSHINPY' or
            key == 'GENSHINPY_HONKAI' or
            key == 'GENSHINPY_STARRAIL') and '{' in value:
            value = json.loads(value)
        return value


config = Config()
