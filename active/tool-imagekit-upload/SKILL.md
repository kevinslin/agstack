---
name: imagekit-upload
description: Upload existing images to ImageKit and return CDN URLs.
dependencies: []
version: 1.0.0
---

# ImageKit Upload

This skill enables uploading images to ImageKit CDN from either local file paths or clipboard contents. The skill returns the uploaded image URL for immediate use.

## Core Rule

Upload only existing image bytes from a real file path or from the clipboard.

If the requested image file cannot be found:
- Stop.
- Ask the user for the exact file path, or ask them to copy the image to the clipboard and confirm.

Do not recreate, redraw, approximate, crop from another image, or generate an SVG fallback.

## Prerequisites

The upload script may be installed under `~/.codex/skills/imagekit-upload`, while
credentials from an older installation remain under
`~/.llm/skills/tool-imagekit-upload/scripts/.env`. This split installation is
supported: the script first checks for `.env` beside `upload.js`, then falls back
to the legacy `.llm` credential file.

Before concluding that credentials are missing, check both locations. Never print
credential values.

For a new setup, create `.env` beside the upload script:

```bash
cd /path/to/imagekit-upload/scripts
cp .env.example .env
```

Then edit `.env` and add your credentials:

- `IMAGEKIT_PUBLIC_KEY`: Your ImageKit public key
- `IMAGEKIT_PRIVATE_KEY`: Your ImageKit private key
- `IMAGEKIT_URL_ENDPOINT`: Your ImageKit URL endpoint (e.g., `https://ik.imagekit.io/your_id`)

Find these in your ImageKit dashboard under Developer Options → API Keys.

## Setup

Install Node.js dependencies from the skill's `scripts` directory:

```bash
cd /path/to/imagekit-upload/scripts
npm install
```

This installs ImageKit SDK, dotenv for configuration, and clipboardy for clipboard support on macOS.

## Usage

### Upload from File Path

When the user provides a file path to an image, use the upload script:

```bash
node ./scripts/upload.js --file "/path/to/image.jpg"
```

Optional parameters:
- `--name "custom-name"`: Custom file name (default: original filename)
- `--folder "/images"`: Upload to specific folder in ImageKit
- `--tags "tag1,tag2"`: Add comma-separated tags

### Upload from Clipboard

When the user wants to upload an image from their clipboard:

```bash
node ./scripts/upload.js --clipboard
```

This reads image data directly from the system clipboard.

## Output

The script outputs a JSON object containing:
- `url`: The full CDN URL of the uploaded image
- `fileId`: The ImageKit file ID
- `name`: The file name
- `size`: File size in bytes

Display the URL prominently to the user for easy copying.

## Error Handling

Common errors:
- **Missing credentials**: Check for `.env` beside `upload.js`, then check `~/.llm/skills/tool-imagekit-upload/scripts/.env`
- **File not found**: Check the file path is correct and accessible
- **Invalid file type**: ImageKit supports common image formats (JPG, PNG, GIF, WebP, SVG)
- **Clipboard empty**: Ensure an image is copied to the clipboard before upload

If the file is not discoverable locally, do not improvise a replacement asset. Ask the user for the missing file path or for a clipboard copy instead.

## When to Use This Skill

Use this skill when:
- User requests to upload an image to ImageKit
- User wants to get a CDN URL for an image
- User says "upload this image" or "put this on ImageKit"
- User provides an image path and mentions ImageKit or CDN
- User wants to upload from clipboard/copy buffer

## Examples

**Example 1: Upload screenshot**
```
User: Upload this screenshot to ImageKit: /tmp/screenshot.png
Assistant: [Uses this skill to upload the file and returns the CDN URL]
```

**Example 2: Upload from clipboard**
```
User: I just copied an image, can you upload it to ImageKit?
Assistant: [Uses this skill with --clipboard flag to upload and returns the CDN URL]
```

**Example 3: Organized upload**
```
User: Upload logo.png to ImageKit in the /brand folder
Assistant: [Uses this skill with --folder "/brand" parameter]
```

**Example 4: Missing attachment file**
```
User: Upload this attached image to ImageKit
Assistant: [Searches for the exact local file. If it cannot be found, stops and asks the user for the file path or to upload from clipboard. Does not recreate the image.]
```
