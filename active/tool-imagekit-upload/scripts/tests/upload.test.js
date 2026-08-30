const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { spawnSync } = require('node:child_process');

const sourceScript = path.resolve(__dirname, '..', 'upload.js');

function writeEnv(filePath, publicKey, endpoint) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(
    filePath,
    [
      `IMAGEKIT_PUBLIC_KEY=${publicKey}`,
      'IMAGEKIT_PRIVATE_KEY=test-private-key',
      `IMAGEKIT_URL_ENDPOINT=${endpoint}`,
      ''
    ].join('\n')
  );
}

function runUpload({ localEnv, legacyEnv }) {
  const testRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'imagekit-upload-test-'));
  const scriptDirectory = path.join(testRoot, 'scripts');
  const homeDirectory = path.join(testRoot, 'home');
  const scriptPath = path.join(scriptDirectory, 'upload.js');
  const imagePath = path.join(testRoot, 'image.png');

  fs.mkdirSync(path.join(scriptDirectory, 'node_modules', 'imagekit'), { recursive: true });
  fs.copyFileSync(sourceScript, scriptPath);
  fs.writeFileSync(imagePath, 'test image');
  fs.writeFileSync(
    path.join(scriptDirectory, 'node_modules', 'imagekit', 'index.js'),
    `module.exports = class ImageKit {
      constructor(config) { this.config = config; }
      async upload(options) {
        return {
          url: this.config.urlEndpoint + '/' + this.config.publicKey,
          fileId: 'test-file-id',
          name: options.fileName,
          size: options.file.length,
          filePath: '/' + options.fileName,
          thumbnailUrl: this.config.urlEndpoint + '/thumbnail'
        };
      }
    };
    `
  );

  if (localEnv) {
    writeEnv(path.join(scriptDirectory, '.env'), localEnv.publicKey, localEnv.endpoint);
  }
  if (legacyEnv) {
    writeEnv(
      path.join(homeDirectory, '.llm', 'skills', 'tool-imagekit-upload', 'scripts', '.env'),
      legacyEnv.publicKey,
      legacyEnv.endpoint
    );
  }

  const environment = { ...process.env, HOME: homeDirectory };
  delete environment.IMAGEKIT_PUBLIC_KEY;
  delete environment.IMAGEKIT_PRIVATE_KEY;
  delete environment.IMAGEKIT_URL_ENDPOINT;

  const result = spawnSync(process.execPath, [scriptPath, '--file', imagePath], {
    encoding: 'utf8',
    env: environment
  });

  fs.rmSync(testRoot, { recursive: true, force: true });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test('uses the legacy credential file when the local file is absent', () => {
  const result = runUpload({
    legacyEnv: { publicKey: 'legacy-key', endpoint: 'https://legacy.example' }
  });

  assert.equal(result.url, 'https://legacy.example/legacy-key');
});

test('prefers the local credential file over the legacy fallback', () => {
  const result = runUpload({
    localEnv: { publicKey: 'local-key', endpoint: 'https://local.example' },
    legacyEnv: { publicKey: 'legacy-key', endpoint: 'https://legacy.example' }
  });

  assert.equal(result.url, 'https://local.example/local-key');
});
