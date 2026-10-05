import time
import asyncio
import re
from bs4 import BeautifulSoup

from py_lead_generation.src.engines.base import BaseEngine
from py_lead_generation.src.engines.abstract import AbstractEngine
from py_lead_generation.src.misc.utils import get_coords_by_location


class GoogleMapsEngine(BaseEngine, AbstractEngine):
    '''
    GoogleMapsEngine

    Google Maps lead scraper.

    The engine searches Google Maps, scrolls through the results,
    collects business URLs, then parses business details.
    '''

    BASE_URL = 'https://www.google.com/maps/search/{query}/@{coords},{zoom}z/data=!3m1!4b1?entry=ttu'

    FIELD_NAMES = [
        'Title',
        'Address',
        'PhoneNumber',
        'WebsiteURL',
        'Rating',
        'ReviewCount',
    ]

    FILENAME = 'google_maps_leads.csv'

    SLEEP_PER_SCROLL_S = 2
    SCROLL_TIME_DURATION_S = 120
    MAX_STALLED_SCROLLS = 3
    END_OF_LIST_MARKERS = ('reached the end of the list',)

    def __init__(
        self,
        query: str,
        location: str,
        zoom: int | float = 12,
        target_count: int | None = None,
        existing_count: int = 0,
        db=None,
    ) -> None:

        self._entries = []

        self.zoom = zoom
        self.query = query
        self.location = location
        self.target_count = target_count
        self.existing_count = existing_count
        self.db = db
        self.min_required_urls = (
            target_count + existing_count + 10
            if target_count is not None
            else None
        )

        self.coords = get_coords_by_location(
            self.location
        )

        self.search_query = (
            f'{self.query}%20{self.location}'
        )

        self.url = self.BASE_URL.format(
            query=self.search_query,
            coords=','.join(self.coords),
            zoom=self.zoom
        )

    async def _get_search_results_urls(
        self
    ) -> list[str]:

        async def hover_search_results() -> None:
            '''
            Try to hover over the Google Maps results panel.

            Google occasionally changes its DOM structure, so
            several selectors are attempted.

            Hovering is helpful for scrolling the results panel,
            but it is not allowed to crash the scraper if the
            selector is unavailable.
            '''

            selectors = [
                '[role="main"]',
                'div[role="feed"]',
                '.m6QErb',
                '.m6QErb.tLjsW.eKbjU',
            ]

            for selector in selectors:

                try:
                    element = await self.page.query_selector(
                        selector
                    )

                    if element:
                        await element.hover()

                        print(
                            f"Google Maps results panel found "
                            f"using selector: {selector}"
                        )

                        await asyncio.sleep(0.5)

                        return

                except Exception:
                    continue

            print(
                "Warning: Could not identify the Google Maps "
                "results panel. Continuing without hover."
            )

        async def scroll_and_sleep(
            delta_y: int = 1000
        ) -> None:

            await self.page.mouse.wheel(
                0,
                delta_y
            )

            await asyncio.sleep(
                self.SLEEP_PER_SCROLL_S
            )

        async def end_of_list_reached() -> bool:
            '''
            True only when Google shows its end-of-list message.

            (The old check returned True as soon as the results panel
            existed, which stopped scrolling after a single scroll.)
            '''

            try:
                feed = await self.page.query_selector(
                    'div[role="feed"]'
                )

                if not feed:
                    return False

                text = (await feed.inner_text()).lower()

            except Exception:
                return False

            return any(
                marker in text
                for marker in self.END_OF_LIST_MARKERS
            )

        async def count_loaded_results() -> int:

            elements = await self.page.query_selector_all(
                'a.hfpxzc'
            )

            return len(elements)

        async def scrape_urls() -> list[str]:

            urls = []

            link_elements = await self.page.query_selector_all(
                'a.hfpxzc'
            )

            for link_element in link_elements:

                url = await link_element.get_attribute(
                    'href'
                )

                if url:
                    urls.append(url)

            return list(dict.fromkeys(urls))

        await hover_search_results()

        start_scroll_time = time.time()

        previous_count = 0
        stalled_scrolls = 0

        while True:

            await scroll_and_sleep()

            current_count = await count_loaded_results()

            print(
                f"Scrolled: {current_count} results loaded"
            )

            if current_count > previous_count:
                previous_count = current_count
                stalled_scrolls = 0
            else:
                stalled_scrolls += 1

            if (
                self.min_required_urls
                and current_count >= self.min_required_urls
            ):
                print(
                    f"Target count reached ({current_count} listings loaded, "
                    f"needed {self.min_required_urls}). Stopping scroll."
                )
                break

            if await end_of_list_reached():
                print("Reached the end of the results list.")
                break

            if stalled_scrolls >= self.MAX_STALLED_SCROLLS:
                print(
                    f"No new results after "
                    f"{self.MAX_STALLED_SCROLLS} scrolls. Stopping."
                )
                break

            if (
                time.time() - start_scroll_time
                > self.SCROLL_TIME_DURATION_S
            ):
                print("Scroll time limit reached. Stopping.")
                break

        urls = await scrape_urls()

        print(
            f"Google Maps business URLs found: {len(urls)}"
        )

        return urls

    def _parse_data_with_soup(
        self,
        html: str
    ) -> list[str]:

        '''
        Parse HTML content to extract:

        [title, address, phone, website]
        '''

        soup = BeautifulSoup(
            html,
            'html.parser'
        )

        selectors = {
            'title': '.DUwDvf.lfPIob',

            'address': '[data-item-id="address"]',

            'phone_number': (
                '[data-item-id^="phone:"]'
            ),

            'website_url': (
                '[data-item-id="authority"]'
            )
        }

        def extract_text(
            selector: str,
            default: str = '',
            cleaner: callable = None
        ) -> str:

            element = soup.select_one(
                selector
            )

            text = (
                element.get_text()
                if element
                else default
            )

            return (
                cleaner(text)
                if cleaner
                else text
            )

        def clean_phone_number(
            text: str
        ) -> str:

            return re.sub(
                r'\D',
                '',
                text
            )

        def clean_address(
            text: str
        ) -> str:

            return (
                text
                .replace('', '')
                .strip()
            )

        def clean_website_url(
            text: str
        ) -> str:

            return (
                text
                .replace('', '')
                .strip()
            )

        cleaners = {
            'phone_number':
                clean_phone_number,

            'address':
                clean_address,

            'website_url':
                clean_website_url
        }

        # Parsing standard fields
        parsed_data = [
            extract_text(
                selectors[key],
                cleaner=cleaners.get(key)
            )
            for key in selectors
        ]

        # Extract Rating (e.g., 4.8)
        rating = ""
        rating_elem = soup.select_one(
            'div.F7nice span[aria-hidden="true"], span.ceNzKf, span.fontDisplayLarge'
        )
        if rating_elem:
            m = re.search(r'\b[1-5]\.\d\b|\b[1-5]\b', rating_elem.get_text().strip())
            if m:
                rating = m.group(0)

        # Extract Review Count (e.g., 142)
        reviews = ""
        review_elem = soup.select_one(
            'div.F7nice span:last-child, button[jsaction*="reviews"], span[aria-label*="reviews"], span[aria-label*="review"]'
        )
        if review_elem:
            rev_digits = re.sub(r'\D', '', review_elem.get_text().strip())
            if rev_digits:
                reviews = rev_digits

        parsed_data.append(rating)
        parsed_data.append(reviews)

        return parsed_data