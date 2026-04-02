from .hris import MockHrisAdapter
from .knowledge import MockKnowledgeAdapter
from .license import MockLicenseAdapter
from .mdm import MockMdmAdapter
from .okta import MockOktaAdapter
from .slack import MockSlackAdapter
from .ticketing import MockTicketingAdapter

__all__ = [
    "MockHrisAdapter",
    "MockKnowledgeAdapter",
    "MockLicenseAdapter",
    "MockMdmAdapter",
    "MockOktaAdapter",
    "MockSlackAdapter",
    "MockTicketingAdapter",
]
