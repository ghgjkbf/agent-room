---
name: markitdown
description: Convert files to Markdown using Microsoft MarkItDown. Handles PDF, DOCX, PPTX, XLSX, images (OCR), audio (transcription), HTML, CSV, JSON, XML, ZIP, EPUB, YouTube, and more. Use when working with non-text files that need to be read, analyzed, or converted.
origin: microsoft/markitdown
---

# MarkItDown — Universal File-to-Markdown Converter

Convert 15+ file formats into clean, token-efficient Markdown using Microsoft's MarkItDown library. Essential for reading PDFs, Office documents, images, audio, and more in a text-native format.

## Quick Start

```bash
# Full install (all optional dependencies)
pip install 'markitdown[all]'

# Minimal install (PDF + Office only)
pip install markitdown
```

## Supported Formats

| Format | Dependency | Notes |
|--------|-----------|-------|
| **PDF** | Built-in | Text extraction, no OCR by default |
| **DOCX** | Built-in | Word documents |
| **PPTX** | `python-pptx` | PowerPoint presentations |
| **XLSX** | `openpyxl` | Excel spreadsheets |
| **HTML** | Built-in | Web pages and HTML files |
| **Images** | `markitdown[all]` | OCR via Azure Document Intelligence |
| **Audio** | `markitdown[all]` | Transcription via Azure Speech / OpenAI Whisper |
| **CSV** | Built-in | Tabular data to markdown tables |
| **JSON** | Built-in | Structured data to markdown |
| **XML** | Built-in | XML documents |
| **ZIP** | Built-in | Archive contents listing |
| **EPUB** | Built-in | E-book format |
| **RTF** | `markitdown[all]` | Rich text format |
| **YouTube** | `yt-dlp` | Video metadata + captions |
| **WAV/MP3** | `pydub` | Audio content via Whisper |

## CLI Usage

```bash
# Convert a single file → stdout
markitdown document.pdf

# Convert and save to file
markitdown document.pdf > output.md
markitdown report.docx -o report.md

# Convert a URL
markitdown https://example.com/page.html -o page.md

# Pipe-friendly
cat document.pdf | markitdown

# YouTube (requires yt-dlp)
markitdown "https://www.youtube.com/watch?v=VIDEO_ID" -o video.md
```

## Python API Usage

```python
from markitdown import MarkItDown

md = MarkItDown()

# From file
result = md.convert("document.pdf")
print(result.text_content)

# From URL
result = md.convert("https://example.com/page.html")
print(result.text_content)

# From stream
with open("file.docx", "rb") as f:
    result = md.convert_stream(f, file_extension=".docx")
    print(result.text_content)
```

### OCR (Images → Text)
```python
from markitdown import MarkItDown
from azure.ai.documentintelligence import DocumentIntelligenceClient

# Requires Azure Document Intelligence endpoint + key
md = MarkItDown(
    document_intelligence_endpoint="https://<resource>.cognitiveservices.azure.com/",
    document_intelligence_client=client
)
result = md.convert("screenshot.png")
print(result.text_content)
```

### Audio Transcription
```python
from markitdown import MarkItDown
from openai import OpenAI

# Requires OpenAI API key
client = OpenAI(api_key="sk-...")
md = MarkItDown(audio_transcription_client=client)
result = md.convert("recording.wav")
print(result.text_content)
```

## Typical Workflow in Claude Code

When a user asks about a non-text file, the workflow is:

```
1. Check file extension → match to supported format
2. Run: markitdown <file> -o <file>.md
3. Read the .md output
4. Answer questions / analyze / refactor based on the text
```

## Batch Conversion Pattern

```bash
# Convert all PDFs in a directory
for f in *.pdf; do
    markitdown "$f" -o "${f%.pdf}.md"
done

# Convert all Office files
for f in *.docx *.pptx *.xlsx; do
    markitdown "$f" -o "${f%.*}.md"
done
```

## Installation Troubleshooting

```bash
# If 'markitdown' command not found, use:
python -m markitdown

# If pip install fails on Windows:
pip install markitdown  # base only, skip audio/ocr

# Verify installation:
markitdown --help
python -c "from markitdown import MarkItDown; print('OK')"
```

## Anti-Patterns

- **Reading binary files directly** — always `markitdown` convert first, then read the `.md`.
- **Trying to OCR without Azure** — base markitdown extracts embedded text only, not image text.
- **Converting huge files without thinking** — large PDFs/audio can produce massive output; trim or paginate.
- **Forgetting the `[all]` install** — image OCR and audio features need `pip install 'markitdown[all]'`.
