from .amazon_canopy import AmazonCanopyAdapter
from .ebay_scraper import EbayScraperAPIAdapter
from .registry import get_adapter_for_url

__all__ = ["AmazonCanopyAdapter", "EbayScraperAPIAdapter", "get_adapter_for_url"]