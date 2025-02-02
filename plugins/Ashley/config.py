import yaml
import json

class AshleyConfig(dict):
    def __init__(self, path='config.yaml'):
        super().__init__()

        # 优先加载上一次的配置
        try:
            with open('db.json', 'r') as db:
                self.update(json.load(db))
        except FileNotFoundError:
            json.dump({}, open('db.json', 'w'))
        except json.JSONDecodeError:
            pass

        # 加载用户配置覆盖过时的配置
        with open('config.yaml', 'r') as conf:
            self.update(yaml.safe_load(conf))

        # 保存配置
        json.dump(self, open('db.json', 'w'))

    def reload(self):
        self.__init__()

    def __getattr__(self, item):
        return self[item]
    
    def __setattr__(self, key, value):
        self[key] = value
        json.dump(self, open('db.json', 'w'))

    def get(self, key, default=None):
        '''获取配置若不存在则返回默认值，并且保存配置'''
        value = super().get(key, default)
        if value is default:
            self[key] = default
            json.dump(self, open('db.json', 'w'))
        return value