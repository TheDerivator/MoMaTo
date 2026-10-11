"""Remarks API: listing, posting rights, replies, editing with history, deleting, images and
their access rules. [RM-1] [RM-2] [RM-3] [RM-4] [RM-5]"""

import re
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from momato.config import Settings
from momato.db.base import utcnow
from momato.db.models import Attachment, DefaultGrant, Post
from momato.db.session import Database
from momato.domain.access import BuiltinRole, Scope
from momato.services.attachments import MAX_ATTACHMENT_BYTES
from momato.services.sample_data import png_image
from tests.api.conftest import ClientFactory, grant, project_node
from tests.helpers import count_statements

PNG = png_image(120, 80, 1)
SENSORS = 4102  # Anna is a member, Tomás the coordinator; Sofia wrote the newest remark


def upload(
    client: TestClient, number: int = SENSORS, data: bytes = PNG, name: str = "map.png"
) -> Any:
    response = client.post(
        f"/api/projects/{number}/attachments", files={"file": (name, data, "image/png")}
    )
    assert response.status_code == 201, response.text
    return response.json()


def remarks(client: TestClient, number: int = SENSORS) -> Any:
    response = client.get(f"/api/projects/{number}/remarks")
    assert response.status_code == 200, response.text
    return response.json()


def post(client: TestClient, text: str, number: int = SENSORS) -> Any:
    response = client.post(f"/api/projects/{number}/remarks", json={"body_md": text})
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- reading


def test_the_sample_remarks_newest_first_with_their_replies(anna: TestClient) -> None:
    body = remarks(anna)
    assert body["count"] == 4
    assert body["can_comment"] is True  # a member
    newest = body["items"][0]
    assert newest["author"]["name"] == "Sofia Lind"
    assert newest["body_md"].startswith("Done:\n- First full week of live data")
    assert len(newest["replies"]) == 2
    created = [r["created_at"] for r in body["items"]]
    assert created == sorted(created, reverse=True)
    replies = [r["created_at"] for r in newest["replies"]]
    assert replies == sorted(replies)  # oldest first
    assert all(r["parent_id"] == newest["id"] and r["replies"] == [] for r in newest["replies"])
    assert "<li>" in newest["html"] and '<img src="api/attachments/' in newest["html"]


def test_listing_does_not_query_per_remark(anna: TestClient) -> None:
    """The number of SQL statements does not grow with the remarks and replies (D-028)."""
    with count_statements() as small:
        remarks(anna)
    for index in range(25):
        remark = post(anna, f"remark {index}")
        anna.post(f"/api/remarks/{remark['id']}/replies", json={"body_md": "reply"})
    with count_statements() as large:
        assert remarks(anna)["count"] == 29
    assert large.count == small.count


def test_the_count_is_the_projects_remark_count(anna: TestClient) -> None:
    assert anna.get(f"/api/projects/{SENSORS}").json()["remark_count"] == remarks(anna)["count"]


def test_a_limit_keeps_the_newest(anna: TestClient) -> None:
    body = anna.get(f"/api/projects/{SENSORS}/remarks", params={"limit": 1}).json()
    assert len(body["items"]) == 1
    assert body["count"] == 4  # the count is of all of them
    assert body["items"][0]["author"]["name"] == "Sofia Lind"


def test_the_sample_image_is_served(anna: TestClient) -> None:
    html = remarks(anna)["items"][0]["html"]
    src = re.search(r'<img src="([^"]+)"', html)
    assert src is not None
    response = anna.get(f"/{src.group(1)}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content.startswith(b"\x89PNG")


def test_reading_an_unknown_project_is_404(anna: TestClient) -> None:
    assert anna.get("/api/projects/999999/remarks").status_code == 404


def test_visitors_get_401(clients: ClientFactory) -> None:
    visitor = clients()
    assert visitor.get(f"/api/projects/{SENSORS}/remarks").status_code == 401
    body = {"body_md": "hello"}
    assert visitor.post(f"/api/projects/{SENSORS}/remarks", json=body).status_code == 401


# ---------------------------------------------------------------- posting


def test_who_may_post(clients: ClientFactory, anna: TestClient) -> None:
    bram = clients("bram.peeters")  # signed in, sees every project, not a member of this one
    assert remarks(bram)["can_comment"] is False
    refused = bram.post(f"/api/projects/{SENSORS}/remarks", json={"body_md": "Looks good"})
    assert refused.status_code == 403
    created = post(anna, "**Done** with @Tomás and #4307")
    assert created["author"]["name"] == "Anna Claes"
    assert created["can_edit"] is True and created["can_delete"] is True
    assert created["parent_id"] is None and created["replies"] == []
    assert '<span class="mention">@Tomás</span>' in created["html"]
    assert 'href="projects/4307"' in created["html"]
    assert remarks(anna)["count"] == 5
    assert remarks(anna)["items"][0]["id"] == created["id"]  # newest first


def test_a_coordinator_without_any_role_may_post(clients: ClientFactory) -> None:
    tomas = clients("tomas.rivera")  # the coordinator: implicit rights (D-014)
    assert post(tomas, "From the coordinator")["author"]["name"] == "Tomás Rivera"


def test_a_project_administrator_of_the_department_may_post(
    clients: ClientFactory, sample_database: Database
) -> None:
    scope = Scope.node(project_node(sample_database, SENSORS))
    grant(sample_database, "bram.peeters", BuiltinRole.PROJECT_ADMIN, scope)
    bram = clients("bram.peeters")
    assert post(bram, "As an administrator")["author"]["name"] == "Bram Peeters"


def test_empty_and_overlong_remarks_are_refused(anna: TestClient) -> None:
    url = f"/api/projects/{SENSORS}/remarks"
    assert anna.post(url, json={"body_md": "   \n "}).status_code == 422
    assert anna.post(url, json={"body_md": "x" * 20_001}).status_code == 422
    assert anna.post(url, json={"body_md": "x" * 20_000}).status_code == 201


# ---------------------------------------------------------------- replies


def test_replies_are_one_level_oldest_first(anna: TestClient) -> None:
    remark = post(anna, "Question: who owns the dashboard?")
    first = anna.post(f"/api/remarks/{remark['id']}/replies", json={"body_md": "I do"})
    assert first.status_code == 201
    assert first.json()["parent_id"] == remark["id"] and first.json()["replies"] == []
    anna.post(f"/api/remarks/{remark['id']}/replies", json={"body_md": "and `Sofia`"})
    listed = remarks(anna)["items"][0]
    assert [r["body_md"] for r in listed["replies"]] == ["I do", "and `Sofia`"]
    assert remarks(anna)["count"] == 5  # replies are not counted

    nested = anna.post(f"/api/remarks/{first.json()['id']}/replies", json={"body_md": "deeper"})
    assert nested.status_code == 422


def test_replies_take_no_images(anna: TestClient) -> None:
    remark = post(anna, "text")
    image = upload(anna)
    refused = anna.post(f"/api/remarks/{remark['id']}/replies", json={"body_md": image["markdown"]})
    assert refused.status_code == 422
    assert "text only" in refused.json()["message"]


def test_only_people_who_may_comment_may_reply(clients: ClientFactory, anna: TestClient) -> None:
    remark = remarks(anna)["items"][0]
    bram = clients("bram.peeters")
    reply = bram.post(f"/api/remarks/{remark['id']}/replies", json={"body_md": "hi"})
    assert reply.status_code == 403
    assert anna.post("/api/remarks/999999/replies", json={"body_md": "hi"}).status_code == 404


# ---------------------------------------------------------------- editing and history


def test_authors_edit_their_own_and_the_earlier_text_is_kept(anna: TestClient) -> None:
    remark = post(anna, "first")
    assert remark["versions"] == 1 and remark["edited_at"] is None
    edited = anna.patch(f"/api/remarks/{remark['id']}", json={"body_md": "second"}).json()
    assert edited["body_md"] == "second" and edited["edited_at"] is not None
    assert edited["versions"] == 2
    anna.patch(f"/api/remarks/{remark['id']}", json={"body_md": "third"})
    history = anna.get(f"/api/remarks/{remark['id']}/history").json()
    assert [(v["rev"], v["body_md"]) for v in history] == [
        (1, "first"),
        (2, "second"),
        (3, "third"),
    ]
    assert all(v["written_by"]["name"] == "Anna Claes" for v in history)
    assert history[0]["html"] == "<p>first</p>\n"


def test_replies_can_be_edited_too_by_their_author(anna: TestClient) -> None:
    remark = post(anna, "text")
    reply = anna.post(f"/api/remarks/{remark['id']}/replies", json={"body_md": "one"}).json()
    edited = anna.patch(f"/api/remarks/{reply['id']}", json={"body_md": "two"}).json()
    assert edited["id"] == reply["id"] and edited["parent_id"] == remark["id"]
    assert edited["body_md"] == "two" and edited["versions"] == 2


def test_nobody_edits_someone_elses_remark_not_even_a_moderator(
    clients: ClientFactory, anna: TestClient, admin: TestClient
) -> None:
    mine = post(anna, "mine")
    sofia = clients("sofia.lind")
    patch = {"body_md": "changed"}
    assert sofia.patch(f"/api/remarks/{mine['id']}", json=patch).status_code == 403
    assert admin.patch(f"/api/remarks/{mine['id']}", json=patch).status_code == 403
    assert anna.patch("/api/remarks/999999", json=patch).status_code == 404
    assert anna.patch(f"/api/remarks/{mine['id']}", json={"body_md": " "}).status_code == 422


def test_history_follows_the_visibility_of_the_project(
    clients: ClientFactory, anna: TestClient, sample_database: Database
) -> None:
    mine = post(anna, "text")
    with sample_database.session(write=True) as session:
        session.execute(delete(DefaultGrant))
    bram = clients("bram.peeters")
    assert bram.get(f"/api/remarks/{mine['id']}/history").status_code == 404
    assert anna.get(f"/api/remarks/{mine['id']}/history").status_code == 200


# ---------------------------------------------------------------- deleting


def test_authors_delete_their_own_and_a_missing_one_is_404(anna: TestClient) -> None:
    remark = post(anna, "to go")
    assert anna.delete(f"/api/remarks/{remark['id']}").status_code == 204
    assert anna.delete(f"/api/remarks/{remark['id']}").status_code == 404
    assert remarks(anna)["count"] == 4


def test_others_cannot_delete_but_administrators_can(
    clients: ClientFactory, anna: TestClient, admin: TestClient
) -> None:
    mine = post(anna, "mine")
    sofia = clients("sofia.lind")
    assert sofia.delete(f"/api/remarks/{mine['id']}").status_code == 403
    flagged = next(r for r in remarks(admin)["items"] if r["id"] == mine["id"])
    assert flagged["can_delete"] is True and flagged["can_edit"] is False
    assert admin.delete(f"/api/remarks/{mine['id']}").status_code == 204


def test_a_deleted_remark_with_replies_stays_as_a_placeholder(anna: TestClient) -> None:
    remark = post(anna, "secret plan " + upload(anna)["markdown"])
    reply = anna.post(f"/api/remarks/{remark['id']}/replies", json={"body_md": "ok"}).json()
    assert anna.delete(f"/api/remarks/{remark['id']}").status_code == 204

    body = remarks(anna)
    placeholder = next(r for r in body["items"] if r["id"] == remark["id"])
    assert placeholder["deleted"] is True
    assert placeholder["author"] is None
    assert placeholder["body_md"] == "" and placeholder["html"] == ""
    assert placeholder["can_edit"] is False and placeholder["can_delete"] is False
    assert [r["id"] for r in placeholder["replies"]] == [reply["id"]]
    assert body["count"] == 4  # the placeholder is not a remark of its own
    assert anna.get(f"/api/remarks/{remark['id']}/history").status_code == 404
    late = anna.post(f"/api/remarks/{remark['id']}/replies", json={"body_md": "late"})
    assert late.status_code == 422

    # Deleting the last reply removes the placeholder too.
    assert anna.delete(f"/api/remarks/{reply['id']}").status_code == 204
    assert all(r["id"] != remark["id"] for r in remarks(anna)["items"])


def test_deleting_a_reply_keeps_a_remark_that_has_other_replies(anna: TestClient) -> None:
    remark = post(anna, "text")
    first = anna.post(f"/api/remarks/{remark['id']}/replies", json={"body_md": "1"}).json()
    anna.post(f"/api/remarks/{remark['id']}/replies", json={"body_md": "2"})
    anna.delete(f"/api/remarks/{remark['id']}")
    anna.delete(f"/api/remarks/{first['id']}")
    placeholder = next(r for r in remarks(anna)["items"] if r["id"] == remark["id"])
    assert [r["body_md"] for r in placeholder["replies"]] == ["2"]


# ---------------------------------------------------------------- preview


def test_preview_renders_like_a_remark(clients: ClientFactory, anna: TestClient) -> None:
    visitor = clients()
    assert visitor.post("/api/markdown/preview", json={"body_md": "**x**"}).status_code == 401
    html = anna.post("/api/markdown/preview", json={"body_md": "**x** #4102"}).json()["html"]
    assert "<strong>x</strong>" in html and 'href="projects/4102"' in html


# ---------------------------------------------------------------- images


def test_upload_then_post_attaches_the_image(anna: TestClient, sample_database: Database) -> None:
    uploaded = upload(anna, name="../../etc/Roll 7 marks.PNG")
    assert uploaded["filename"] == "Roll 7 marks.png"
    assert uploaded["url"] == f"api/attachments/{uploaded['id']}/Roll%207%20marks.png"
    assert uploaded["markdown"] == f"![Roll 7 marks.png]({uploaded['url']})"
    remark = post(anna, f"Chatter marks:\n\n{uploaded['markdown']}")
    assert f'<img src="{uploaded["url"]}"' in remark["html"]
    with sample_database.session() as session:
        attachment = session.scalars(
            select(Attachment).where(Attachment.public_id == uploaded["id"])
        ).one()
        assert attachment.post_id == remark["id"]
    assert anna.get(f"/{uploaded['url']}").status_code == 200


def test_someone_elses_draft_is_not_claimed(
    clients: ClientFactory, anna: TestClient, sample_database: Database
) -> None:
    sofia = clients("sofia.lind")
    theirs = upload(sofia)
    post(anna, f"borrowed {theirs['markdown']}")
    with sample_database.session() as session:
        attachment = session.scalars(
            select(Attachment).where(Attachment.public_id == theirs["id"])
        ).one()
        assert attachment.post_id is None


def test_only_real_images_of_limited_size(anna: TestClient) -> None:
    url = f"/api/projects/{SENSORS}/attachments"
    fake = anna.post(url, files={"file": ("x.png", b"not a png", "image/png")})
    assert fake.status_code == 422
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>'
    assert anna.post(url, files={"file": ("x.svg", svg, "image/svg+xml")}).status_code == 422
    huge = PNG + b"\0" * MAX_ATTACHMENT_BYTES
    too_big = anna.post(url, files={"file": ("big.png", huge, "image/png")})
    assert too_big.status_code == 422 and "at most 10 MB" in too_big.json()["message"]
    for name, data, extension in [
        ("a", b"GIF89a" + b"\0" * 20, ".gif"),
        ("b", b"\xff\xd8\xff" + b"\0" * 20, ".jpg"),
        ("c", b"RIFF\0\0\0\0WEBP" + b"\0" * 20, ".webp"),
    ]:
        sent = anna.post(url, files={"file": (name, data, "")})
        assert sent.status_code == 201 and sent.json()["filename"] == name + extension


def test_uploading_needs_the_right_to_comment(clients: ClientFactory) -> None:
    files = {"file": ("map.png", PNG, "image/png")}
    url = f"/api/projects/{SENSORS}/attachments"
    assert clients().post(url, files=files).status_code == 401
    assert clients("bram.peeters").post(url, files=files).status_code == 403
    missing = clients("anna.claes").post("/api/projects/999999/attachments", files=files)
    assert missing.status_code == 404


def test_images_are_only_served_to_people_who_see_the_project(
    clients: ClientFactory, anna: TestClient, sample_database: Database
) -> None:
    url = upload(anna)["url"]
    with sample_database.session(write=True) as session:
        session.execute(delete(DefaultGrant))  # nobody is a Viewer by default any more
    bram = clients("bram.peeters")
    assert bram.get(f"/{url}").status_code == 404
    assert clients().get(f"/{url}").status_code == 401
    assert anna.get(f"/{url}").status_code == 200  # a member sees it
    assert anna.get("/api/attachments/" + "0" * 32 + "/x.png").status_code == 404


def test_drafts_nobody_posted_are_cleaned_up(
    anna: TestClient, sample_settings: Settings, sample_database: Database
) -> None:
    old = upload(anna)
    with sample_database.session(write=True) as session:
        session.execute(
            update(Attachment)
            .where(Attachment.public_id == old["id"])
            .values(created_at=utcnow() - timedelta(days=2))
        )
    assert (sample_settings.uploads_dir / old["id"]).exists()
    upload(anna)  # any new upload sweeps old drafts
    assert not (sample_settings.uploads_dir / old["id"]).exists()
    assert anna.get(f"/{old['url']}").status_code == 404


def test_deleting_a_remark_or_a_project_removes_its_files(
    admin: TestClient, sample_settings: Settings, sample_database: Database
) -> None:
    first = upload(admin)
    remark = post(admin, first["markdown"])
    assert admin.delete(f"/api/remarks/{remark['id']}").status_code == 204
    assert not (sample_settings.uploads_dir / first["id"]).exists()

    boot = admin.get("/api/bootstrap").json()
    root = boot["org"][0]["id"]
    anna_id = next(p["id"] for p in boot["people"] if p["name"] == "Anna Claes")
    created = admin.post(
        "/api/projects",
        json={
            "name": "Scratch",
            "org_node_id": root,
            "coordinator_id": anna_id,
            "start_date": "2026-11-02",
            "end_date": "2027-01-29",
        },
    )
    assert created.status_code == 201, created.text
    second = upload(admin, created.json()["number"])
    post(admin, second["markdown"], created.json()["number"])
    assert (sample_settings.uploads_dir / second["id"]).exists()
    assert admin.delete(f"/api/projects/{created.json()['number']}").status_code == 204
    assert not (sample_settings.uploads_dir / second["id"]).exists()
    with sample_database.session() as session:
        leftover = session.scalars(select(Post).where(Post.body_md == second["markdown"])).first()
        assert leftover is None
