# ImageKit Upload Skill

A generic agent skill for uploading images to ImageKit CDN from file paths or clipboard.

## Setup

### 1. Navigate to Scripts Directory

```bash
cd /path/to/imagekit-upload/scripts
```

### 2. Install Dependencies

Install required packages:

```bash
npm install
```

This installs:
- `imagekit` - ImageKit SDK
- `dotenv` - Environment variable management
- `clipboardy` - Clipboard support for macOS

### 3. Configure Credentials

Credentials should normally be stored in `.env` beside `./scripts/upload.js`.
When the script is installed under `~/.codex/skills/imagekit-upload` but an
older credential file remains at
`~/.llm/skills/tool-imagekit-upload/scripts/.env`, the script uses that legacy
file as a fallback. Check both locations before reporting missing credentials,
and never print credential values.

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit the `.env` file and add your ImageKit credentials:

```bash
IMAGEKIT_PUBLIC_KEY=your_public_key_here
IMAGEKIT_PRIVATE_KEY=your_private_key_here
IMAGEKIT_URL_ENDPOINT=https://ik.imagekit.io/your_id
```

You can find these credentials in your ImageKit dashboard under **Developer Options** → **API Keys**.

### 4. Test the Skill

Try uploading a test image:

```bash
node ./scripts/upload.js --file "/path/to/test-image.jpg"
```

## Usage Examples

### Upload from file path

```bash
# Basic upload
node ./scripts/upload.js --file "/path/to/image.jpg"

# Upload with custom name
node ./scripts/upload.js --file "/path/to/image.jpg" --name "my-custom-name"

# Upload to specific folder
node ./scripts/upload.js --file "/path/to/image.jpg" --folder "/brand/logos"

# Upload with tags
node ./scripts/upload.js --file "/path/to/image.jpg" --tags "logo,brand,2024"

# Combine options
node ./scripts/upload.js --file "/path/to/image.jpg" --name "company-logo" --folder "/brand" --tags "logo,primary"
```

### Upload from clipboard

```bash
# Upload image from clipboard
node ./scripts/upload.js --clipboard

# Upload from clipboard with custom name
node ./scripts/upload.js --clipboard --name "screenshot-$(date +%Y%m%d)"
```

## Using with an Agent

Once set up, you can use this skill by invoking it in your agent environment:

```
User: Upload this screenshot to ImageKit: /tmp/screenshot.png
Agent: [Invokes skill and uploads the image]

User: I just copied an image, upload it to ImageKit
Agent: [Uses --clipboard flag to upload from clipboard]
```

## Troubleshooting

### "Missing required environment variables"

Check for `.env` beside `./scripts/upload.js`, then check
`~/.llm/skills/tool-imagekit-upload/scripts/.env`. One of those files must
contain all three required variables.

### "ImageKit SDK not installed"

Run `npm install` in the scripts directory.

### "File not found"

Verify the file path is correct and the file exists.

### "Failed to read image from clipboard"

This feature currently only works on macOS. Make sure you've copied an image to your clipboard before running the command.

## Supported Image Formats

- JPEG (.jpg, .jpeg)
- PNG (.png)
- GIF (.gif)
- WebP (.webp)
- SVG (.svg)
- And other formats supported by ImageKit

## Output

The script returns a JSON object with:

```json
{
  "success": true,
  "url": "https://ik.imagekit.io/your_id/image.jpg",
  "fileId": "abc123...",
  "name": "image.jpg",
  "size": 123456,
  "filePath": "/image.jpg",
  "thumbnailUrl": "https://ik.imagekit.io/your_id/tr:n-media_library_thumbnail/image.jpg"
}
```

The `url` field contains the CDN URL you can use to access your image.
