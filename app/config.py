from config import get_config, Config as RootConfig, DevelopmentConfig, ProductionConfig, TestingConfig

# Backward-compatible exports for app imports
Config = RootConfig
get_config = get_config
DevelopmentConfig = DevelopmentConfig
ProductionConfig = ProductionConfig
TestingConfig = TestingConfig
