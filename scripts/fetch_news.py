import html
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import argostranslate.package
import argostranslate.translate


ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120 Safari/537.36 "
    "PC-GAMING-NOW/1.0"
)

with open(
    os.path.join(ROOT, "config.json"),
    encoding="utf-8",
) as file:
    config = json.load(file)


def clean(value):
    value = html.unescape(value or "")

    value = re.sub(
        r"<script.*?</script>",
        " ",
        value,
        flags=re.I | re.S,
    )

    value = re.sub(
        r"<style.*?</style>",
        " ",
        value,
        flags=re.I | re.S,
    )

    value = re.sub(r"<[^>]+>", " ", value)

    return re.sub(r"\s+", " ", value).strip()


def get_text(element, names):
    for name in names:
        child = element.find(name)

        if child is not None and child.text:
            return clean(child.text)

    return ""


def parse_date(value):
    try:
        return parsedate_to_datetime(value).astimezone(
            timezone.utc
        )
    except Exception:
        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).astimezone(timezone.utc)
        except Exception:
            return datetime.now(timezone.utc)


def contains_japanese(value):
    return bool(
        re.search(
            r"[\u3040-\u30ff\u3400-\u9fff]",
            value or "",
        )
    )


def normalize_image_url(image_url, page_url):
    image_url = html.unescape(image_url or "").strip()

    if not image_url:
        return ""

    image_url = urljoin(page_url, image_url)

    if not image_url.startswith(("http://", "https://")):
        return ""

    return image_url


def image_from_html(html_text, page_url):
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
        r'<img[^>]+src=["\']([^"\']+)["\']',
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            html_text,
            flags=re.I | re.S,
        )

        if match:
            image_url = normalize_image_url(
                match.group(1),
                page_url,
            )

            if image_url:
                return image_url

    return ""


def fetch_article_image(page_url):
    if not page_url:
        return ""

    try:
        request = urllib.request.Request(
            page_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:
            content_type = response.headers.get(
                "Content-Type",
                "",
            )

            if "text/html" not in content_type:
                return ""

            raw_html = response.read(
                1_500_000
            ).decode(
                "utf-8",
                errors="ignore",
            )

        return image_from_html(
            raw_html,
            page_url,
        )

    except Exception as error:
        print(
            "Image page error:",
            page_url,
            error,
        )

        return ""


def image_from_description(description, article_url):
    if not description:
        return ""

    match = re.search(
        r'<img[^>]+src=["\']([^"\']+)["\']',
        description,
        flags=re.I | re.S,
    )

    if not match:
        return ""

    return normalize_image_url(
        match.group(1),
        article_url,
    )


def get_rss_image(item, article_url, raw_description):
    media_content = item.find(
        "{http://search.yahoo.com/mrss/}content"
    )

    if media_content is not None:
        image_url = normalize_image_url(
            media_content.attrib.get("url", ""),
            article_url,
        )

        medium = media_content.attrib.get(
            "medium",
            "",
        )

        content_type = media_content.attrib.get(
            "type",
            "",
        )

        if image_url and (
            medium == "image"
            or content_type.startswith("image/")
            or not medium
        ):
            return image_url

    media_thumbnail = item.find(
        "{http://search.yahoo.com/mrss/}thumbnail"
    )

    if media_thumbnail is not None:
        image_url = normalize_image_url(
            media_thumbnail.attrib.get("url", ""),
            article_url,
        )

        if image_url:
            return image_url

    enclosure = item.find("enclosure")

    if enclosure is not None:
        enclosure_type = enclosure.attrib.get(
            "type",
            "",
        )

        enclosure_url = normalize_image_url(
            enclosure.attrib.get("url", ""),
            article_url,
        )

        if enclosure_url and (
            enclosure_type.startswith("image/")
            or re.search(
                r"\.(jpg|jpeg|png|webp)(?:\?|$)",
                enclosure_url,
                flags=re.I,
            )
        ):
            return enclosure_url

    return image_from_description(
        raw_description,
        article_url,
    )


def install_translation_model():
    installed_languages = (
        argostranslate.translate.get_installed_languages()
    )

    english = next(
        (
            language
            for language in installed_languages
            if language.code == "en"
        ),
        None,
    )

    japanese = next(
        (
            language
            for language in installed_languages
            if language.code == "ja"
        ),
        None,
    )

    if english and japanese:
        return

    print("Installing English-Japanese model...")

    argostranslate.package.update_package_index()

    packages = (
        argostranslate.package.get_available_packages()
    )

    translation_package = next(
        (
            package
            for package in packages
            if package.from_code == "en"
            and package.to_code == "ja"
        ),
        None,
    )

    if translation_package is None:
        raise RuntimeError(
            "English-Japanese translation model "
            "was not found."
        )

    model_path = translation_package.download()

    argostranslate.package.install_from_path(
        model_path
    )

    print("Translation model installed.")


def translate_to_japanese(value):
    value = clean(value)

    if not value or contains_japanese(value):
        return value

    try:
        return argostranslate.translate.translate(
            value,
            "en",
            "ja",
        )
    except Exception as error:
        print(
            "Translation error:",
            error,
        )

        return value


def read_feed(feed):
    request = urllib.request.Request(
        feed["url"],
        headers={
            "User-Agent": USER_AGENT,
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=30,
    ) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)

    articles = []

    for item in root.findall(".//item")[:20]:
        title = get_text(
            item,
            ["title"],
        )

        url = get_text(
            item,
            ["link"],
        )

        raw_description = ""

        for description_name in [
            "description",
            "{http://purl.org/rss/1.0/modules/content/}"
            "encoded",
        ]:
            description_element = item.find(
                description_name
            )

            if (
                description_element is not None
                and description_element.text
            ):
                raw_description = (
                    description_element.text
                )
                break

        description = clean(
            raw_description
        )

        published = get_text(
            item,
            [
                "pubDate",
                "published",
                "updated",
            ],
        )

        if not title or not url:
            continue

        rss_image = get_rss_image(
            item,
            url,
            raw_description,
        )

        articles.append(
            {
                "title": title,
                "summary": description,
                "url": url,
                "image": rss_image,
                "published": parse_date(
                    published
                ).isoformat(),
                "source": feed["name"],
                "category": feed["category"],
            }
        )

    return articles


def main():
    install_translation_model()

    collected = []

    for feed in config["feeds"]:
        try:
            collected.extend(
                read_feed(feed)
            )
        except Exception as error:
            print(
                "Feed error:",
                feed["name"],
                error,
            )

    collected.sort(
        key=lambda article: article["published"],
        reverse=True,
    )

    seen = set()
    unique_articles = []

    for article in collected:
        duplicate_key = re.sub(
            r"\W",
            "",
            article["title"],
        ).lower()

        if duplicate_key in seen:
            continue

        seen.add(duplicate_key)
        unique_articles.append(article)

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(
            hours=config.get("hours", 36)
        )
    )

    recent_articles = [
        article
        for article in unique_articles
        if parse_date(
            article["published"]
        ) >= cutoff
    ]

    recent_articles = recent_articles[
        : config.get("max_articles", 12)
    ]

    for number, article in enumerate(
        recent_articles,
        start=1,
    ):
        print(
            f"Processing {number}/"
            f"{len(recent_articles)}:",
            article["title"],
        )

        original_title = article["title"]
        original_summary = clean(
            article["summary"]
        )[:500]

        article["title_original"] = (
            original_title
        )

        article["title"] = (
            translate_to_japanese(
                original_title
            )
        )

        article["summary"] = (
            translate_to_japanese(
                original_summary
            )[:180]
        )

        if not article.get("image"):
            print(
                "Finding image:",
                article["url"],
            )

            article["image"] = (
                fetch_article_image(
                    article["url"]
                )
            )

        if article.get("image"):
            print(
                "Image found:",
                article["image"],
            )
        else:
            print(
                "No image found:",
                article["url"],
            )

    output = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "articles": recent_articles,
    }

    output_path = os.path.join(
        ROOT,
        "data",
        "news.json",
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        "Updated, translated and imaged:",
        len(recent_articles),
    )


if __name__ == "__main__":
    main()
