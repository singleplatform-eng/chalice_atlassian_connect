__version__ = '0.0.6.dev0'
__url__ = 'https://github.com/singleplatform-eng/chalice_atlassian_connect'
__author__ = 'Gavin Mogan, SinglePlatform Engineering Team'
__email__ = 'techservices@singleplatform.com'
__all__ = ['AtlassianConnect', 'AtlassianConnectClient']

from .base import AtlassianConnect  # NOQA: E402, F401, C0413
from .client import AtlassianConnectClient  # NOQA: E402, F401, C0413
