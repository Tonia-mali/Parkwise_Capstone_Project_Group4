const fs = require('fs');
const path = require('path');

// Read index.html
const indexPath = path.join(__dirname, 'index.html');
let html = fs.readFileSync(indexPath, 'utf8');

// Map of placeholder -> environment variable name
const keys = {
  '__GOOGLE_MAPS_KEY__': 'GOOGLE_MAPS_KEY',
  '__GEMINI_KEY_1__':    'GEMINI_KEY_1',
  '__GEMINI_KEY_2__':    'GEMINI_KEY_2',
  '__GEMINI_KEY_3__':    'GEMINI_KEY_3',
};

let missing = [];

for (const [placeholder, envVar] of Object.entries(keys)) {
  const value = process.env[envVar];
  if (!value) {
    missing.push(envVar);
  } else {
    html = html.replaceAll(placeholder, value);
    console.log(`✓ Injected ${envVar}`);
  }
}

if (missing.length > 0) {
  console.error(`\n✗ Missing environment variables:\n  ${missing.join('\n  ')}`);
  console.error('\nSet these in Vercel dashboard → Settings → Environment Variables\n');
  process.exit(1); // Fail the build so bad deploys are caught
}

// Write output to dist/index.html
const distDir = path.join(__dirname, 'dist');
if (!fs.existsSync(distDir)) fs.mkdirSync(distDir);

const pdSrc = path.join(__dirname, 'parkingData.js');
if (fs.existsSync(pdSrc)) {
  fs.copyFileSync(pdSrc, path.join(distDir, 'parkingData.js'));
  console.log('✓ Copied parkingData.js');
}

fs.writeFileSync(path.join(distDir, 'index.html'), html);
console.log('\n✓ Build complete → dist/index.html');
