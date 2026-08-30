#!/usr/bin/env node

/**
 * ImageKit Upload Script
 *
 * Uploads images to ImageKit from file paths or clipboard
 *
 * Usage:
 *   node upload.js --file "/path/to/image.jpg" [--name "custom-name"] [--folder "/folder"] [--tags "tag1,tag2"]
 *   node upload.js --clipboard [--name "custom-name"] [--folder "/folder"] [--tags "tag1,tag2"]
 */

const fs = require('fs');
const path = require('path');

// Prefer credentials installed with this script, then fall back to the legacy skill path.
const localEnvPath = path.join(__dirname, '.env');
const legacyEnvPath = path.join(
  process.env.HOME || '',
  '.llm/skills/tool-imagekit-upload/scripts/.env'
);
const envPath = [localEnvPath, legacyEnvPath].find(candidate => fs.existsSync(candidate));

if (envPath) {
  if (typeof process.loadEnvFile === 'function') {
    process.loadEnvFile(envPath);
  } else {
    try {
      require('dotenv').config({ path: envPath });
    } catch (err) {
      // Older Node versions need dotenv unless credentials are already exported.
    }
  }
}

// Parse command-line arguments
function parseArgs() {
  const args = process.argv.slice(2);
  const options = {
    file: null,
    clipboard: false,
    name: null,
    folder: null,
    tags: null
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--file':
        options.file = args[++i];
        break;
      case '--clipboard':
        options.clipboard = true;
        break;
      case '--name':
        options.name = args[++i];
        break;
      case '--folder':
        options.folder = args[++i];
        break;
      case '--tags':
        options.tags = args[++i];
        break;
      default:
        console.error(`Unknown argument: ${args[i]}`);
        process.exit(1);
    }
  }

  return options;
}

// Validate environment variables
function validateEnvironment() {
  const required = ['IMAGEKIT_PUBLIC_KEY', 'IMAGEKIT_PRIVATE_KEY', 'IMAGEKIT_URL_ENDPOINT'];
  const missing = required.filter(key => !process.env[key]);

  if (missing.length > 0) {
    console.error(JSON.stringify({
      error: 'Missing required environment variables',
      missing: missing,
      message: 'Please set IMAGEKIT_PUBLIC_KEY, IMAGEKIT_PRIVATE_KEY, and IMAGEKIT_URL_ENDPOINT'
    }, null, 2));
    process.exit(1);
  }
}

// Main upload function
async function upload() {
  const options = parseArgs();

  // Validate inputs
  if (!options.file && !options.clipboard) {
    console.error(JSON.stringify({
      error: 'Must specify either --file or --clipboard'
    }, null, 2));
    process.exit(1);
  }

  if (options.file && options.clipboard) {
    console.error(JSON.stringify({
      error: 'Cannot specify both --file and --clipboard'
    }, null, 2));
    process.exit(1);
  }

  validateEnvironment();

  // Lazy-load dependencies (in case they're not installed)
  let ImageKit;
  try {
    ImageKit = require('imagekit');
  } catch (err) {
    console.error(JSON.stringify({
      error: 'ImageKit SDK not installed',
      message: 'Run: npm install imagekit',
      details: err.message
    }, null, 2));
    process.exit(1);
  }

  // Initialize ImageKit
  const imagekit = new ImageKit({
    publicKey: process.env.IMAGEKIT_PUBLIC_KEY,
    privateKey: process.env.IMAGEKIT_PRIVATE_KEY,
    urlEndpoint: process.env.IMAGEKIT_URL_ENDPOINT
  });

  try {
    let fileContent;
    let fileName;

    if (options.file) {
      // Upload from file path
      if (!fs.existsSync(options.file)) {
        console.error(JSON.stringify({
          error: 'File not found',
          path: options.file
        }, null, 2));
        process.exit(1);
      }

      fileContent = fs.readFileSync(options.file);
      fileName = options.name || path.basename(options.file);
    } else {
      // Upload from clipboard
      let clipboardy;
      try {
        clipboardy = require('clipboardy');
      } catch (err) {
        console.error(JSON.stringify({
          error: 'Clipboardy not installed',
          message: 'Run: npm install clipboardy',
          details: err.message
        }, null, 2));
        process.exit(1);
      }

      // On macOS, we can try to read clipboard image data
      // This is a simplified approach - for production, you might need platform-specific handling
      try {
        const { execSync } = require('child_process');

        // Try to get clipboard image on macOS using osascript
        const tempFile = '/tmp/imagekit-clipboard-temp.png';
        execSync(`osascript -e 'set theFile to (open for access POSIX file "${tempFile}" with write permission)' -e 'try' -e 'write (the clipboard as «class PNGf») to theFile' -e 'end try' -e 'close access theFile'`);

        if (!fs.existsSync(tempFile)) {
          throw new Error('No image in clipboard');
        }

        fileContent = fs.readFileSync(tempFile);
        fileName = options.name || `clipboard-${Date.now()}.png`;

        // Clean up temp file
        fs.unlinkSync(tempFile);
      } catch (err) {
        console.error(JSON.stringify({
          error: 'Failed to read image from clipboard',
          message: 'Make sure an image is copied to your clipboard',
          details: err.message
        }, null, 2));
        process.exit(1);
      }
    }

    // Build upload options
    const uploadOptions = {
      file: fileContent,
      fileName: fileName
    };

    if (options.folder) {
      uploadOptions.folder = options.folder;
    }

    if (options.tags) {
      uploadOptions.tags = options.tags.split(',').map(t => t.trim());
    }

    // Perform upload
    const result = await imagekit.upload(uploadOptions);

    // Output success result
    console.log(JSON.stringify({
      success: true,
      url: result.url,
      fileId: result.fileId,
      name: result.name,
      size: result.size,
      filePath: result.filePath,
      thumbnailUrl: result.thumbnailUrl
    }, null, 2));

  } catch (err) {
    console.error(JSON.stringify({
      error: 'Upload failed',
      message: err.message,
      details: err.toString()
    }, null, 2));
    process.exit(1);
  }
}

// Run the upload
upload();
