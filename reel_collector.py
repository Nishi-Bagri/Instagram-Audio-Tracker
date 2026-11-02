
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
BROWSER_PROFILE_DIR = BASE_DIR / "browser_profile"


def normalize_reel_url(url):
    return url.split("?")[0].rstrip("/") + "/"


def collect_reel_links(
    audio_url,
    audio_folder,
    max_scrolls=300,
    no_new_limit=10
):
    audio_folder = Path(audio_folder)
    audio_folder.mkdir(parents=True, exist_ok=True)

    links_file = audio_folder / "collected_reel_links.txt"

    existing_links = []

    if links_file.exists():
        existing_links = [
            normalize_reel_url(line.strip())
            for line in links_file.read_text(
                encoding="utf-8-sig"
            ).splitlines()
            if line.strip()
        ]

    existing_set = set(existing_links)
    new_links_set = set()

    no_growth_streak = 0

    print("Previously collected links:", len(existing_set))

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
        )

        try:
            page = (
                context.pages[0]
                if context.pages
                else context.new_page()
            )

            print("\nOpening Instagram audio page...")

            response = page.goto(
                audio_url,
                wait_until="domcontentloaded",
                timeout=60000
            )

            print(
                "HTTP Status:",
                response.status if response else None
            )

            page.wait_for_timeout(5000)

            for scroll_number in range(1, max_scrolls + 1):

                hrefs = page.locator("a[href]").evaluate_all(
                    """elements =>
                        elements.map(element => element.href)
                    """
                )

                reel_hrefs = [
                    href for href in hrefs
                    if "/reel/" in href
                ]

                clean_dom_links = {
                    normalize_reel_url(href)
                    for href in reel_hrefs
                }

                overlap_count = len(clean_dom_links & existing_set)
                unknown_count = len(clean_dom_links - existing_set)

                print("Unique Reel links in DOM:", len(clean_dom_links))
                print("Sample DOM URLs:", list(clean_dom_links)[:5])
                print("Already collected in DB/file:", overlap_count)
                print("Not previously collected:", unknown_count)

                scroll_new_links = []

                for href in hrefs:

                    if "/reel/" not in href:
                        continue

                    clean_url = normalize_reel_url(href)

                    if (
                        clean_url not in existing_set
                        and clean_url not in new_links_set
                    ):
                        new_links_set.add(clean_url)
                        scroll_new_links.append(clean_url)

                # Save new URLs immediately
                if scroll_new_links:
                    with links_file.open(
                        "a",
                        encoding="utf-8"
                    ) as file:
                        for link in scroll_new_links:
                            file.write(link + "\n")

                    no_growth_streak = 0

                else:
                    no_growth_streak += 1

                total_unique = (
                    len(existing_set) + len(new_links_set)
                )

                print(
                    f"Scroll {scroll_number}/{max_scrolls} | "
                    f"New this scroll: {len(scroll_new_links)} | "
                    f"New total: {len(new_links_set)} | "
                    f"Total unique: {total_unique} | "
                    f"No-growth streak: {no_growth_streak}"
                )

                if no_growth_streak >= no_new_limit:
                    print(
                        "\nStopping: No new Reels found in "
                        f"{no_new_limit} consecutive scrolls."
                    )
                    break

                # Scroll to trigger Instagram's lazy loading
                page.mouse.wheel(0, 2500)
                page.wait_for_timeout(3000)

                scroll_height = page.evaluate(
                    "document.documentElement.scrollHeight"
                )

                scroll_position = page.evaluate(
                    "window.scrollY"
                )

                print("Page height:", scroll_height)
                print("Scroll position:", scroll_position)

        finally:
            context.close()

    total_links = len(existing_set) + len(new_links_set)

    print("\n=== COLLECTION SUMMARY ===")
    print("Previously collected:", len(existing_set))
    print("New links discovered:", len(new_links_set))
    print("Total unique links:", total_links)
    print("Saved file:", links_file)

    return {
        "previous_links": len(existing_set),
        "new_links": len(new_links_set),
        "total_links": total_links,
        "links_file": links_file,
    }
