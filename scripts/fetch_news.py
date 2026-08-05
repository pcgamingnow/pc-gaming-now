import html
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import argostranslate.package
import argostranslate.translate


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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

    packages = argostranslate.package.get_available_packages()

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
            "English-Japanese translation model was not found."
        )

    model_path = translation_package.download()

    argostranslate.package.install_from_path(model_path)

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
        print("Translation error:", error)

        # 翻訳失敗時は英語の原文を残す
        return value


def read_feed(feed):
    request = urllib.request.Request(
        feed["url"],
        headers={
            "User-Agent": "PC-GAMING-NOW/1.0",
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
        title = get_text(item, ["title"])
        url = get_text(item, ["link"])

        description = get_text(
            item,
            [
                "description",
                "{http://purl.org/rss/1.0/modules/content/}"
                "encoded",
            ],
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

        articles.append(
            {
                "title": title,
                "summary": description,
                "url": url,
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
            collected.extend(read_feed(feed))
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

    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=config.get("hours", 36)
    )

    recent_articles = [
        article
        for article in unique_articles
        if parse_date(article["published"]) >= cutoff
    ]

    recent_articles = recent_articles[
        : config.get("max_articles", 12)
    ]

    for number, article in enumerate(
        recent_articles,
        start=1,
    ):
        print(
            f"Translating {number}/{len(recent_articles)}:",
            article["title"],
        )

        original_title = article["title"]
        original_summary = clean(article["summary"])[:500]

        article["title_original"] = original_title
        article["title"] = translate_to_japanese(
            original_title
        )

        article["summary"] = translate_to_japanese(
            original_summary
        )[:180]

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
        "Updated and translated:",
        len(recent_articles),
    )


if __name__ == "__main__":
    main()
