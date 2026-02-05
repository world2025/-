import asyncio
import time
from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from pypdf import PdfWriter

import main


def make_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.mark.asyncio
async def test_healthz_ok() -> None:
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_convert_pdf_success_returns_markdown_page_header() -> None:
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("demo.pdf", make_pdf_bytes(), "application/pdf")}
        response = await client.post("/convert", files=files)

    assert response.status_code == 200
    assert "# 第 1 页" in response.text


@pytest.mark.asyncio
async def test_convert_rejects_non_pdf() -> None:
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("demo.txt", b"hello", "text/plain")}
        response = await client.post("/convert", files=files)

    assert response.status_code == 400
    assert response.json()["detail"] == "仅支持 PDF 文件"


def test_text_to_markdown_heading_and_blankline_rules() -> None:
    source = "TITLE\n\n\ncontent"
    result = main.text_to_markdown(source)
    assert result == "## Title\n\ncontent"


@pytest.mark.asyncio
async def test_convert_endpoint_handles_requests_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_converter(_: bytes) -> str:
        time.sleep(0.2)
        return "# ok\n"

    monkeypatch.setattr(main, "pdf_to_markdown", slow_converter)

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async def one_call() -> int:
            files = {"file": ("demo.pdf", b"%PDF-1.4 test", "application/pdf")}
            response = await client.post("/convert", files=files)
            return response.status_code

        started = time.perf_counter()
        statuses = await asyncio.gather(*(one_call() for _ in range(5)))
        duration = time.perf_counter() - started

    assert statuses == [200, 200, 200, 200, 200]
    assert duration < 0.7


@pytest.mark.asyncio
async def test_convert_returns_429_when_queue_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    old_sem = main.conversion_semaphore
    old_timeout = main.CONVERSION_ACQUIRE_TIMEOUT_SECONDS
    main.conversion_semaphore = asyncio.Semaphore(1)
    main.CONVERSION_ACQUIRE_TIMEOUT_SECONDS = 0.05

    def very_slow_converter(_: bytes) -> str:
        time.sleep(0.2)
        return "# ok\n"

    monkeypatch.setattr(main, "pdf_to_markdown", very_slow_converter)

    try:
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async def one_call() -> int:
                files = {"file": ("demo.pdf", b"%PDF-1.4 test", "application/pdf")}
                response = await client.post("/convert", files=files)
                return response.status_code

            statuses = await asyncio.gather(one_call(), one_call())
        assert 429 in statuses
    finally:
        main.conversion_semaphore = old_sem
        main.CONVERSION_ACQUIRE_TIMEOUT_SECONDS = old_timeout
