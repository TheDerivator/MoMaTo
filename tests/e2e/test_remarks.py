"""The Remarks tab in a real browser: composer, template, images and the lightbox, replies, edits
with history, deleting, links. [RM-1] [RM-2] [RM-3] [RM-4] [RM-5]"""

import re

from playwright.sync_api import Page, expect

from momato.services.sample_data import png_image
from tests.e2e.conftest import remember, sign_in

SENSORS = 4102  # Anna is a member and wrote the second remark; Sofia wrote the newest
PNG = png_image(120, 80, 3)


def open_remarks(
    page: Page, base: str, *, username: str = "anna.claes", number: int = SENSORS
) -> None:
    remember(page)
    page.goto(f"{base}projects/{number}/remarks")
    sign_in(page, username)
    expect(page.get_by_role("link", name=re.compile("^Remarks"))).to_have_attribute(
        "aria-current", "page"
    )
    expect(cards(page).first).to_be_visible()  # the list has loaded


def cards(page: Page):
    return page.locator("article.remark")


def composer(page: Page):
    return page.get_by_label("Write a remark")


def remark_by(page: Page, name: str):
    """The remark cards whose own author (not a replier) is `name`."""
    return cards(page).filter(has=page.locator(".remark__main > .remark__who", has_text=name))


def paste_image(page: Page, label: str = "Write a remark") -> None:
    page.get_by_label(label).evaluate(
        """(area, bytes) => {
            const data = new DataTransfer();
            data.items.add(new File([new Uint8Array(bytes)], "pasted.png", { type: "image/png" }));
            area.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
        }""",
        list(PNG),
    )


# ---------------------------------------------------------------- reading


def test_remarks_are_listed_newest_first_with_replies_and_an_image(
    sample_server: str, page: Page
) -> None:
    open_remarks(page, sample_server)
    expect(cards(page)).to_have_count(4)
    first = cards(page).first
    expect(first).to_contain_text("Sofia Lind")
    expect(first.locator("li").first).to_contain_text("First full week of live data")
    expect(first.locator(".reply")).to_have_count(2)
    image = first.locator(".md img")
    expect(image).to_be_visible()
    assert page.evaluate("document.querySelector('.md img').naturalWidth") > 0  # it really loads
    assert first.locator(".remark__who .remark__when").first.text_content().strip() in {  # type: ignore[union-attr]
        "Today",
        "Yesterday",
        "6 days ago",
        "5 days ago",
        "4 days ago",
        "3 days ago",
        "2 Oct 2026",
    }


def test_a_click_on_an_image_opens_the_lightbox_and_any_click_or_escape_closes_it(
    sample_server: str, page: Page
) -> None:
    open_remarks(page, sample_server)
    cards(page).first.locator(".md img").click()
    box = page.get_by_role("dialog", name=re.compile("^Image"))
    expect(box).to_be_visible()
    page.keyboard.press("Escape")
    expect(box).to_have_count(0)

    cards(page).first.locator(".md img").click()
    expect(box).to_be_visible()
    box.locator(".lightbox__image").click()
    expect(box).to_have_count(0)

    cards(page).first.locator(".md img").click()
    page.get_by_role("button", name="Close image").click()
    expect(box).to_have_count(0)


def test_a_viewer_reads_but_cannot_post_or_reply(sample_server: str, page: Page) -> None:
    open_remarks(page, sample_server, username="bram.peeters")
    expect(cards(page)).to_have_count(4)
    expect(page.get_by_text("You can read remarks here.")).to_be_visible()
    expect(page.get_by_role("button", name="Post remark")).to_have_count(0)
    expect(page.get_by_role("button", name="Reply")).to_have_count(0)
    expect(page.get_by_role("button", name="Edit")).to_have_count(0)


# ---------------------------------------------------------------- posting


def test_the_template_chip_inserts_done_and_next_steps_and_posting_adds_the_card(
    sample_server: str, page: Page
) -> None:
    open_remarks(page, sample_server)
    page.get_by_role("button", name="Done / Next steps template").click()
    expect(composer(page)).to_have_value("Done:\n- \n\nNext steps:\n- ")
    expect(composer(page)).to_be_focused()
    page.keyboard.type("Rolled out to line 2")
    page.get_by_role("button", name="Post remark").click()

    expect(cards(page)).to_have_count(5)
    expect(cards(page).first).to_contain_text("Anna Claes")
    expect(cards(page).first.locator("li").first).to_have_text("Rolled out to line 2")
    expect(cards(page).first.locator(".remark__when")).to_have_text("Today")
    expect(page.get_by_role("link", name=re.compile("^Remarks"))).to_contain_text("5")
    expect(composer(page)).to_have_value("")  # the composer is clear again


def test_ctrl_enter_posts(sample_server: str, page: Page) -> None:
    open_remarks(page, sample_server)
    composer(page).fill("Posted with the keyboard")
    composer(page).press("Control+Enter")
    expect(cards(page).first).to_contain_text("Posted with the keyboard")
    expect(cards(page)).to_have_count(5)


def test_an_empty_remark_cannot_be_posted(sample_server: str, page: Page) -> None:
    open_remarks(page, sample_server)
    expect(page.get_by_role("button", name="Post remark")).to_be_disabled()
    composer(page).fill("   ")
    expect(page.get_by_role("button", name="Post remark")).to_be_disabled()


def test_preview_renders_markdown_like_the_post_will_be(sample_server: str, page: Page) -> None:
    open_remarks(page, sample_server)
    composer(page).fill("**Strong** and @Tomás on #4307\n\n- one\n- two")
    page.get_by_role("button", name="Preview").click()
    preview = page.locator(".composer__preview")
    expect(preview.locator("strong")).to_have_text("Strong")
    expect(preview.locator(".mention")).to_have_text("@Tomás")
    expect(preview.locator("a.project-ref")).to_have_text("#4307")
    expect(preview.locator("li")).to_have_count(2)
    page.get_by_role("button", name="Write", exact=True).click()
    expect(composer(page)).to_have_value("**Strong** and @Tomás on #4307\n\n- one\n- two")


def test_the_toolbar_formats_the_selection(sample_server: str, page: Page) -> None:
    open_remarks(page, sample_server)
    composer(page).fill("make this bold")
    composer(page).evaluate("el => el.setSelectionRange(5, 9)")
    page.get_by_role("button", name="Bold").click()
    expect(composer(page)).to_have_value("make **this** bold")
    page.get_by_role("button", name="Bulleted list").click()
    expect(composer(page)).to_have_value("- make **this** bold")


def test_a_pasted_image_is_uploaded_inserted_and_shown_after_posting(
    sample_server: str, page: Page
) -> None:
    open_remarks(page, sample_server)
    composer(page).fill("Dashboard draft:")
    paste_image(page)
    chip = page.locator(".file-chip", has_text="pasted.png")
    expect(chip).to_be_visible()
    expect(composer(page)).to_have_value(
        re.compile(
            r"Dashboard draft:\n!\[pasted\.png\]\(api/attachments/[0-9a-f]{32}/pasted\.png\)"
        )
    )

    page.get_by_role("button", name="Post remark").click()
    expect(cards(page)).to_have_count(5)
    image = cards(page).first.locator(".md img")
    expect(image).to_be_visible()
    assert page.evaluate("document.querySelector('article.remark .md img').naturalWidth") == 120
    image.click()
    expect(page.get_by_role("dialog", name=re.compile("^Image"))).to_be_visible()


def test_an_image_chosen_with_the_button_can_be_removed_again(
    sample_server: str, page: Page
) -> None:
    open_remarks(page, sample_server)
    page.get_by_label("Choose images").set_input_files(
        {"name": "map.png", "mimeType": "image/png", "buffer": PNG}
    )
    chip = page.locator(".file-chip", has_text="map.png")
    expect(chip).to_be_visible()
    expect(composer(page)).to_have_value(re.compile(r"!\[map\.png\]"))
    chip.get_by_role("button", name="Remove map.png").click()
    expect(chip).to_have_count(0)
    expect(composer(page)).to_have_value("")


def test_a_file_that_is_not_an_image_is_refused_with_a_message(
    sample_server: str, page: Page
) -> None:
    open_remarks(page, sample_server)
    page.get_by_label("Choose images").set_input_files(
        {"name": "fake.png", "mimeType": "image/png", "buffer": b"this is not a png"}
    )
    expect(page.get_by_role("alert")).to_contain_text("only PNG, JPEG, GIF or WebP")
    expect(page.locator(".file-chip")).to_have_count(0)


def test_an_unsent_draft_survives_a_reload(sample_server: str, page: Page) -> None:
    open_remarks(page, sample_server)
    composer(page).fill("Not sent yet")
    page.reload()
    expect(composer(page)).to_have_value("Not sent yet")
    composer(page).fill("")
    page.reload()
    expect(composer(page)).to_have_value("")


# ---------------------------------------------------------------- replies


def test_replying_posts_with_enter_and_escape_cancels(sample_server: str, page: Page) -> None:
    open_remarks(page, sample_server)
    card = cards(page).first
    before = card.locator(".reply").count()

    card.get_by_role("button", name="Reply").click()
    box = card.get_by_label("Write a reply")
    expect(box).to_be_focused()
    box.fill("Not this one")
    page.keyboard.press("Escape")
    expect(card.get_by_label("Write a reply")).to_have_count(0)
    expect(card.locator(".reply")).to_have_count(before)

    card.get_by_role("button", name="Reply").click()
    card.get_by_label("Write a reply").fill("Sensors 7 and 8 next")
    page.keyboard.press("Enter")
    expect(card.locator(".reply")).to_have_count(before + 1)
    expect(card.locator(".reply").last).to_contain_text("Sensors 7 and 8 next")
    expect(card.locator(".reply").last).to_contain_text("Anna Claes")
    expect(page.get_by_role("link", name=re.compile("^Remarks"))).to_contain_text(
        "4"
    )  # replies are not remarks


def test_shift_enter_starts_a_new_line_in_a_reply(sample_server: str, page: Page) -> None:
    open_remarks(page, sample_server)
    card = cards(page).first
    card.get_by_role("button", name="Reply").click()
    box = card.get_by_label("Write a reply")
    box.fill("first")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("second")
    expect(box).to_have_value("first\nsecond")
    page.keyboard.press("Enter")
    expect(card.locator(".reply").last).to_contain_text("second")


# ---------------------------------------------------------------- editing and deleting


def test_editing_shows_edited_and_the_earlier_version(sample_server: str, page: Page) -> None:
    open_remarks(page, sample_server)
    mine = remark_by(page, "Anna Claes").first
    original = mine.locator(".remark__main > .md").inner_text().strip()
    mine.get_by_role("button", name="Edit", exact=True).click()
    editor = page.get_by_label("Edit remark")
    editor.fill("Installation on sections 1 to 4 finished.")
    page.get_by_role("button", name="Save").click()

    mine = remark_by(page, "Anna Claes").filter(
        has_text="Installation on sections 1 to 4 finished."
    )
    expect(mine).to_have_count(1)
    edited = mine.get_by_role("button", name="edited")
    expect(edited).to_be_visible()
    edited.click()
    history = mine.get_by_role("list", name="Versions of this remark")
    expect(history.locator("li")).to_have_count(2)
    expect(history.locator("li").first).to_contain_text("Version 1")
    expect(history.locator("li").first).to_contain_text(original.split("\n")[0])
    expect(history.locator("li").last).to_contain_text("Current")


def test_others_remarks_have_no_edit_or_delete(sample_server: str, page: Page) -> None:
    open_remarks(page, sample_server)
    theirs = remark_by(page, "Sofia Lind").first
    expect(theirs.get_by_role("button", name="Edit", exact=True)).to_have_count(0)
    expect(theirs.get_by_role("button", name="Delete", exact=True)).to_have_count(0)


def test_deleting_asks_first_and_a_remark_with_replies_stays_as_deleted(
    sample_server: str, page: Page
) -> None:
    open_remarks(page, sample_server)
    composer(page).fill("A remark that will get a reply")
    page.get_by_role("button", name="Post remark").click()
    expect(cards(page)).to_have_count(5)
    mine = cards(page).first
    mine.get_by_role("button", name="Reply").click()
    mine.get_by_label("Write a reply").fill("Agreed")
    page.keyboard.press("Enter")
    expect(mine.locator(".reply")).to_have_count(1)

    mine.get_by_role("button", name="Delete", exact=True).first.click()
    dialog = page.get_by_role("dialog", name="Delete this remark?")
    expect(dialog).to_contain_text("Its replies stay")
    dialog.get_by_role("button", name="Cancel").click()
    expect(cards(page).first).to_contain_text("A remark that will get a reply")

    mine.get_by_role("button", name="Delete", exact=True).first.click()
    page.get_by_role("dialog", name="Delete this remark?").get_by_role(
        "button", name="Delete"
    ).click()
    deleted = page.locator("article.remark--deleted")
    expect(deleted).to_have_count(1)
    expect(deleted).to_contain_text("Remark deleted")
    expect(deleted.locator(".reply")).to_have_count(1)
    expect(page.get_by_role("link", name=re.compile("^Remarks"))).to_contain_text("4")

    # deleting the last reply makes the placeholder go too
    deleted.get_by_role("button", name="Delete", exact=True).click()
    page.get_by_role("dialog", name="Delete this reply?").get_by_role(
        "button", name="Delete"
    ).click()
    expect(page.locator("article.remark--deleted")).to_have_count(0)


# ---------------------------------------------------------------- links


def test_a_project_number_in_a_remark_links_to_that_project(sample_server: str, page: Page) -> None:
    open_remarks(page, sample_server)
    composer(page).fill("Same approach as #4307")
    page.get_by_role("button", name="Post remark").click()
    link = cards(page).first.locator("a.project-ref")
    expect(link).to_have_attribute("href", "projects/4307")
    link.click()
    expect(page).to_have_url(re.compile(r"/projects/4307$"))
    expect(page.locator(".project-title")).to_have_text("Digital shift handover")
