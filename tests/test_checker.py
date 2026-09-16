import yts_checker_service as svc

HTML = """
<html><body>
  <a href="/torrent/download/abc.torrent" title="Inception 1080p BluRay x265">1080p.BluRay.x265</a>
  <a href="https://cdn.example/def.torrent">720p WEB</a>
  <a href="/movies/other">not a torrent</a>
</body></html>
"""


def test_slugify_and_candidate_urls():
    assert svc.slugify_title_for_yts("  Spider-Man: No Way Home! ") == "spider-man-no-way-home"
    assert svc.build_candidate_urls("Inception", "2010") == [f"{b}/inception-2010" for b in svc.SITE_BASES]


def test_normalize_tokens():
    meta = svc.normalize_tokens(["2160p", "WEB-DL", "HEVC"])
    assert (meta["quality"], meta["source"], meta["codec"]) == ("2160p", "WEB", "x265")
    assert svc.normalize_tokens([])["quality"] == "unknown"


def test_extract_torrents_from_html():
    found = svc.extract_torrents_from_html("https://yts.example/movies/inception-2010", HTML)
    assert [t["torrent_url"] for t in found] == [
        "https://yts.example/torrent/download/abc.torrent",
        "https://cdn.example/def.torrent",
    ]
    assert (found[0]["quality"], found[0]["source"], found[0]["codec"]) == ("1080p", "BLURAY", "x265")
    assert (found[1]["quality"], found[1]["source"]) == ("720p", "WEB")


def test_check_endpoint(monkeypatch):
    monkeypatch.setattr(svc, "fetch_page", lambda url: (True, 200, HTML))
    monkeypatch.setattr(
        svc,
        "lightweight_validate_url",
        lambda url: {"ok": True, "status": 200, "final_url": url, "content_type": "x", "content_length": "10"},
    )
    client = svc.app.test_client()

    assert client.get("/health").json == {"status": "ok"}
    assert client.post("/check", data="nope").status_code == 400
    assert client.post("/check", json={"items": "x"}).status_code == 400

    resp = client.post("/check", json={"items": [{"imdbID": "tt1375666", "title": "Inception", "year": "2010"}]})
    result = resp.json["results"]["tt1375666"]
    assert len(result["torrents"]) == 2
    assert result["checked_urls"][0]["status"] == 200
