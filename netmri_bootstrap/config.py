import os
import json
from dataclasses import dataclass
from infoblox_netmri.client import InfobloxNetMRI

_config = None
# Note that we cannot just pick latest version because different
# versions of API tend to, well, differ. Here we assume the customer
# uses reasonably recent (7.0+) version of NetMRI.
# Any change in this version must be tested before it's rolled out.
NETMRI_API_VERSION = "3.1"

_client = None

def get_config():
    global _config
    if _config is None:
        base_path = os.path.dirname(os.path.realpath(__file__))
        config_fn = os.path.join(base_path, 'config.json')
        with open(config_fn, 'r') as config_fh:
            config_data = json.load(config_fh)
        _config = BootstrapperConfig(**config_data)
    return _config

def get_api_client():
    global _client
    conf = get_config()
    if _client is None:
        _client = InfobloxNetMRI(
            conf.host,
            conf.username,
            conf.password,
            api_version=NETMRI_API_VERSION
        )

    return _client

@dataclass
class BootstrapperConfig:
    host: str
    username: str
    password: str
    scripts_root: str
    bootstrap_branch: str
    skip_readonly_objects: bool
    class_paths: dict
