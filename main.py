import asyncio
from contextlib import asynccontextmanager
from io import BytesIO
import os
import re

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from pypdf import PdfReader

app = FastAPI(title="PDF to Markdown")

# Tunable capacity controls.
MAX_CONCURRENT_CONVERSIONS = int(os.getenv("MAX_CONCURRENT_CONVERSIONS", "8"))
CONVERSION_ACQUIRE_TIMEOUT_SECONDS = float(os.getenv("CONVERSION_ACQUIRE_TIMEOUT_SECONDS", "10"))
conversion_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CONVERSIONS)


@asynccontextmanager
async def conversion_slot():
    try:
        await asyncio.wait_for(
            conversion_semaphore.acquire(),
            timeout=CONVERSION_ACQUIRE_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=429, detail="服务繁忙，请稍后重试") from exc

    try:
        yield
    finally:
        conversion_semaphore.release()


def text_to_markdown(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned = []
    for line in lines:
        if not line.strip():
            cleaned.append("")
            continue
        # Convert likely headings (all caps short lines) into markdown headings.
        if len(line.strip()) < 80 and line.strip().isupper():
            cleaned.append(f"## {line.strip().title()}")
            continue
        cleaned.append(line)

    markdown = "\n".join(cleaned)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    return markdown


def pdf_to_markdown(pdf_data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(pdf_data))
    except Exception as exc:  # pragma: no cover - library-level parse errors
        raise HTTPException(status_code=400, detail="无法解析 PDF 文件") from exc

    if not reader.pages:
        raise HTTPException(status_code=400, detail="PDF 文件没有可读取的页面")

    sections = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        page_md = text_to_markdown(page_text)
        sections.append(f"# 第 {page_number} 页\n\n{page_md}" if page_md else f"# 第 {page_number} 页")

    return "\n\n".join(sections).strip() + "\n"


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>PDF 转 Markdown</title>
    <style>
      body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem; }
      .box { max-width: 720px; margin: auto; border: 1px solid #ddd; border-radius: 12px; padding: 1.5rem; }
      button { padding: 0.65rem 1rem; border-radius: 8px; border: 0; background: #2563eb; color: white; cursor: pointer; }
      button:disabled { background: #9ca3af; cursor: not-allowed; }
      .tip { color: #666; margin-top: 0.5rem; }
      .error { color: #b91c1c; margin-top: 1rem; }
    </style>
  </head>
  <body>
    <div class="box">
      <h1>上传 PDF，导出 Markdown</h1>
      <form id="upload-form">
        <input id="pdf" type="file" name="file" accept="application/pdf" required />
        <div style="margin-top: 1rem">
          <button id="submit" type="submit">转换并下载</button>
        </div>
      </form>
      <p class="tip">说明：会按“每页一个一级标题”生成 Markdown。</p>
      <p id="error" class="error"></p>
    </div>

    <script>
      const form = document.getElementById('upload-form');
      const error = document.getElementById('error');
      const submit = document.getElementById('submit');

      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        error.textContent = '';
        submit.disabled = true;

        try {
          const input = document.getElementById('pdf');
          if (!input.files.length) {
            throw new Error('请先选择 PDF 文件。');
          }

          const formData = new FormData();
          formData.append('file', input.files[0]);

          const resp = await fetch('/convert', { method: 'POST', body: formData });
          if (!resp.ok) {
            const payload = await resp.json().catch(() => ({}));
            throw new Error(payload.detail || '转换失败，请重试。');
          }

          const text = await resp.text();
          const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          const originalName = input.files[0].name.replace(/\.pdf$/i, '');
          a.href = url;
          a.download = `${originalName || 'output'}.md`;
          a.click();
          URL.revokeObjectURL(url);
        } catch (err) {
          error.textContent = err.message;
        } finally {
          submit.disabled = false;
        }
      });
    </script>
  </body>
</html>
"""


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/convert", response_class=PlainTextResponse)
async def convert(file: UploadFile = File(...)) -> str:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")

    async with conversion_slot():
        markdown = await asyncio.to_thread(pdf_to_markdown, data)
    return markdown
