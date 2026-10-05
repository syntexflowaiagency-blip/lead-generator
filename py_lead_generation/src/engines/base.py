import asyncio
from playwright.async_api import Playwright, async_playwright, TimeoutError as PlaywrightTimeoutError

from py_lead_generation.src.misc.writer import CsvWriter
from py_lead_generation.src.engines.playwright_config import PlaywrightEngineConfig


class BaseEngine(PlaywrightEngineConfig):
    '''
    `BaseEngine`

    Base engine class expressing methods, which are shared between all engines.
    '''

    async def run(self) -> None:
        '''
        Uses headless webdriver powered by Playwright.

        Creates a web URL based on initialized parameters.

        Parses results by given query and URL one by one.

        Assigns collected results to `.entries`.
        '''

        async with async_playwright() as playwright:

            self.playwright: Playwright = playwright

            await self._setup_browser()

            # Open the initial Google Maps search page.
            await self._open_url_and_wait(
                self.url,
                3,
            )

            # Find business URLs.
            urls: list[str] = await self._get_search_results_urls()

            # Open and parse each business.
            self._entries: list[dict] = (
                await self._get_search_results_entries(
                    urls,
                    db=getattr(self, "db", None),
                )
            )

            await self.browser.close()

    def save_to_csv(
        self,
        filename: str = None,
    ) -> None:
        '''
        Save collected entries to CSV.
        '''

        if filename:
            self.FILENAME = filename

        if not self.FILENAME.endswith(".csv"):
            raise ValueError(
                "Use .csv file extension"
            )

        if not self._entries:
            raise NotImplementedError(
                "Entries are empty, call .run() method first to save them"
            )

        csv_writer = CsvWriter(
            self.FILENAME,
            self.FIELD_NAMES,
        )

        csv_writer.append(
            self._entries
        )

    @property
    def entries(self) -> list[dict]:
        '''
        Returns collected entries once `.run()` was called.
        '''

        if not self._entries:
            raise NotImplementedError(
                "Entries are empty, call .run() method first to create them"
            )

        return self._entries

    @entries.setter
    def entries(self, _) -> None:
        '''
        Prevent direct modification of entries.
        '''

        raise ValueError(
            "Cannot set value to data. This is not allowed"
        )

    async def _open_url_and_wait(
        self,
        url: str,
        sleep_duration_s: float = 3,
    ) -> bool:
        '''
        Open a URL safely.

        Returns:
            True  -> page opened successfully
            False -> navigation failed/timed out

        A failed individual URL does not stop the entire scrape.
        '''

        try:

            await self.page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            await asyncio.sleep(
                sleep_duration_s
            )

            return True

        except PlaywrightTimeoutError:

            print(
                f"Warning: Timeout while opening URL:"
            )

            print(
                f"  {url}"
            )

            print(
                "Skipping this business and continuing..."
            )

            return False

        except Exception as e:

            print(
                f"Warning: Failed to open URL:"
            )

            print(
                f"  {url}"
            )

            print(
                f"  Error: {type(e).__name__}: {e}"
            )

            print(
                "Skipping this business and continuing..."
            )

            return False

    async def _get_search_results_entries(
        self,
        urls: list[str],
        db=None,
        target_needed: int | None = None,
    ) -> list[dict]:
        '''
        Goes over each Google Maps business URL.

        If a URL is already present in the database, it is skipped
        immediately without wasting time on browser page navigation.
        '''

        entries = []
        total_urls = len(urls)

        for index, url in enumerate(
            urls,
            start=1,
        ):
            # Pre-filter already known URLs before navigation (Feature 4)
            if db and db.is_url_duplicate(url):
                print(
                    f"[{index}/{total_urls}] Skipping already scraped business (in database): {url[:60]}..."
                )
                continue

            print(
                f"Processing business "
                f"{index}/{total_urls}..."
            )

            success = await self._open_url_and_wait(
                url,
                1.5,
            )

            # ------------------------------------------------
            # Skip failed navigation
            # ------------------------------------------------

            if not success:
                continue

            try:

                html = await self.page.content()

                data = self._parse_data_with_soup(
                    html
                )

                entry = dict(
                    zip(
                        self.FIELD_NAMES,
                        data,
                    )
                )
                entry["MapsLink"] = url

                entries.append(
                    entry
                )

            except Exception as e:

                print(
                    "Warning: Could not parse business page."
                )

                print(
                    f"  Error: {type(e).__name__}: {e}"
                )

                print(
                    "Skipping this business and continuing..."
                )

        print(
            f"Successfully parsed "
            f"{len(entries)} businesses."
        )

        return entries