from abc import ABC, abstractmethod


class MarketplaceAdapter(ABC):
    """Common interface for marketplace-specific commerce data sources."""

    name: str

    @abstractmethod
    def can_handle_url(self, url: str) -> bool:
        """Return whether this adapter can fetch data for the given URL."""

    @abstractmethod
    def extract_listing_id(self, url: str) -> str | None:
        """Extract the marketplace-native listing identifier from a URL."""

    @abstractmethod
    def product_url(self, listing_id: str) -> str:
        """Build a canonical product URL for the marketplace listing."""

    @abstractmethod
    def fetch_product_profile(self, listing_id: str) -> dict:
        """Fetch product, brand, and review data for a listing."""

    @abstractmethod
    def search_similar_products(self, search_term: str) -> list:
        """Search marketplace listings by a normalized search term."""
