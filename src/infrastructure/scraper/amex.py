from __future__ import annotations

import csv
import re
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from playwright.sync_api import (
    BrowserContext,
    Locator,
    Page,
    Response,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from domain.entity import Expenditure
from infrastructure.config import AmexScraperSettings


class AmexScraper:
    """Playwright-backed scraper for AmEx activity exports."""

    def __init__(self, config: AmexScraperSettings) -> None:
        self.config = config

    def scrape(self, from_date: date, to_date: date) -> list[Expenditure]:
        return self.parse(self.download(from_date, to_date))

    def parse(self, path: Path) -> list[Expenditure]:
        with path.open(encoding="utf-8-sig", newline="") as activity_file:
            return [
                Expenditure(
                    transaction_date=datetime.strptime(row["Datum"], "%m/%d/%Y").date(),
                    description=row["Beskrivning"],
                    card_member=row["Kortmedlem"],
                    account_number=row["Konto #"],
                    amount=Decimal(row["Belopp"].replace("−", "-").replace(",", ".")),
                    extended_details=row["Utökade specifikationer"] or None,
                    statement_description=row["Visas på ditt kontoutdrag som"] or None,
                    address=row["Adress"] or None,
                    city=row["Ort"] or None,
                    postal_code=row["Postnummer"] or None,
                    country=row["Land"] or None,
                    reference=row["Referens"],
                )
                for row in csv.DictReader(activity_file)
                if row["Datum"]
            ]

    def download(self, from_date: date, to_date: date) -> Path:
        download_dir = self.config.download_dir.expanduser().resolve()
        download_dir.mkdir(parents=True, exist_ok=True)
        profile_dir = self.config.profile_dir.expanduser().resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                profile_dir,
                accept_downloads=True,
                args=["--disable-blink-features=AutomationControlled"],
                channel=self.config.chrome_channel,
                chromium_sandbox=True,
                headless=self.config.headless,
                ignore_default_args=["--enable-automation"],
                locale=self.config.locale,
                no_viewport=True,
                timezone_id=self.config.timezone_id,
            )
            page = context.pages[0] if context.pages else context.new_page()

            try:
                self.login(page, context)
                self.wait(page)
                self.search(page, from_date, to_date)
                return self.save(page, from_date, to_date, download_dir)
            finally:
                click_if_visible(
                    page.get_by_role("link", name=re.compile("Logga Ut|Logga ut"))
                )
                context.close()

    def login(self, page: Page, context: BrowserContext) -> None:
        rejected_login_response: list[Response] = []

        def capture_login_rejection(response: Response) -> None:
            if (
                re.search(r"/myca/logon/.*/action/login", response.url)
                and response.status >= 400
            ):
                rejected_login_response.append(response)

        context.on("response", capture_login_rejection)
        page.goto(self.config.login_url, wait_until="domcontentloaded")
        click_if_visible(
            page.locator("#user-consent-management-granular-banner-decline-all-button")
        )
        page.locator("#eliloUserID").fill(self.config.username.get_secret_value())
        page.locator("#eliloPassword").fill(self.config.password.get_secret_value())
        page.locator("#loginSubmit").click()

        try:
            page.wait_for_url("https://global.americanexpress.com/**", timeout=15_000)
        except PlaywrightTimeoutError:
            if rejected_login_response:
                response = rejected_login_response[-1]
                raise RuntimeError(
                    f"AmEx rejected the login request with HTTP {response.status}: "
                    f"{response.url}"
                ) from None
        finally:
            context.remove_listener("response", capture_login_rejection)

    def wait(self, page: Page) -> None:
        mfa_notified = False
        started = time.monotonic()

        while time.monotonic() - started < self.config.login_timeout_seconds:
            page.wait_for_timeout(1_000)

            if page.url.startswith("https://global.americanexpress.com/"):
                return

            content = " ".join(
                (page.locator("body").text_content(timeout=2_000) or "").split()
            )
            if re.search("Säkerhetsverifiering: Lita på enhet", content, re.I):
                page.get_by_role("button", name="Fortsätt").click()
            elif not mfa_notified and re.search(
                "Bekräfta din identitet|push-meddelande", content, re.I
            ):
                print("MFA required. Approve the AmEx push notification.", flush=True)
                mfa_notified = True

        raise TimeoutError(
            f"Timed out waiting for AmEx authentication. Last URL: {page.url}"
        )

    def search(self, page: Page, from_date: date, to_date: date) -> None:
        page.goto(
            f"{self.config.search_url}?from={from_date.isoformat()}"
            f"&to={to_date.isoformat()}",
            wait_until="domcontentloaded",
        )
        page.get_by_role("button", name=re.compile("^Sök$")).click(timeout=10_000)
        page.get_by_role("button", name="Ladda ner").first.wait_for(
            state="visible", timeout=60_000
        )

    def save(
        self,
        page: Page,
        from_date: date,
        to_date: date,
        download_dir: Path,
    ) -> Path:
        page.get_by_role("button", name="Ladda ner").first.click()
        click_if_visible(
            page.locator(
                'label[for="axp-activity-download-body-selection-options-type_csv"]'
            ),
            timeout=10_000,
        )

        all_details = page.locator(
            "#axp-activity-download-body-checkbox-options-includeAll"
        )
        if all_details.count() and not all_details.is_checked():
            page.locator(
                'label[for="axp-activity-download-body-checkbox-options-includeAll"]'
            ).click(timeout=10_000)

        with page.expect_download(timeout=60_000) as download_info:
            page.get_by_role("button", name="Hämta").first.click()

        download = download_info.value
        filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", download.suggested_filename)
        path = (
            download_dir
            / f"activity-{from_date.isoformat()}_to_{to_date.isoformat()}-{filename}"
        )
        download.save_as(path)
        return path


def click_if_visible(locator: Locator, timeout: int = 5_000) -> None:
    try:
        locator.click(timeout=timeout)
    except PlaywrightTimeoutError:
        pass
