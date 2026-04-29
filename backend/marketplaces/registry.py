from .amazon_canopy import AmazonCanopyAdapter
from .base import MarketplaceAdapter

MARKETPLACE_ADAPTERS: tuple[MarketplaceAdapter, ...] = (
    AmazonCanopyAdapter(),
)


def get_adapter_for_url(url: str) -> MarketplaceAdapter:
    for adapter in MARKETPLACE_ADAPTERS:
        if adapter.can_handle_url(url):
            return adapter

    supported = ", ".join(adapter.name for adapter in MARKETPLACE_ADAPTERS)
    raise ValueError(f"Unsupported marketplace URL. Supported marketplaces: {supported}.")
