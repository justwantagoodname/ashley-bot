import yaml


class Config(dict):
    def __init__(self):
        with open('config.yaml', 'r') as conf:
            data = yaml.safe_load(conf)
            super().__init__(data)

    def refresh(self):
        self.__init__()


config = Config()

if __name__ == '__main__':
    for (k, v) in config['Group']:
        print(k, v)
