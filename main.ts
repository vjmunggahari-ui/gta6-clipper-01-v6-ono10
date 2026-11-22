// gta6-clipper-01 v6 entry (Node 22, standard library only).
//
// The entry is the video itself: an AI-made GTA 6 clip (a supercar launches
// off the Vice City bridge and lands on a moving yacht), posted public on
// YouTube as a Short with the bounty's line and the entrant's play code in
// its description. VIDEO.json at the repository root names the video, and
// this program copies it to /output/VIDEO.json, where the gate reads it.
// Nothing this program writes about the video is scored: the house reads
// the video's views through the YouTube Data API and writes its counts to
// /output/video.counts.json after this program's runs.
//
// After copying, the program reads its own output back and checks it:
// the file must parse as JSON, hold a YouTube video address (shorts, watch
// or youtu.be, with an 11-character video id), and stay within the gate's
// 16,384-byte cap. The check's result is written to /output/dossier.json
// next to the copy, so a grader-like run can verify the program did what
// it claims. Any failure exits 1.
//
// Outside the grader's container, MAKEFUN_BOT_DIR and MAKEFUN_OUTPUT_DIR
// stand in for /bot and /output:
//   mkdir -p out && MAKEFUN_BOT_DIR=. MAKEFUN_OUTPUT_DIR=out node main.ts

import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';

const COMPETITION = 'gta6-clipper-01';
const VIDEO_JSON_MAX_BYTES = 16384;
const YOUTUBE_URL =
  /^https:\/\/(?:www\.|m\.)?(?:youtube\.com\/(?:shorts\/|watch\?v=)|youtu\.be\/)([A-Za-z0-9_-]{11})(?:[?&#].*)?$/;

const BOT_DIR = process.env.MAKEFUN_BOT_DIR ?? '/bot';
const OUTPUT_DIR = process.env.MAKEFUN_OUTPUT_DIR ?? '/output';

function fail(message: string): never {
  console.error(`main.ts: ${message}`);
  process.exit(1);
}

mkdirSync(OUTPUT_DIR, { recursive: true });

const sourcePath = join(BOT_DIR, 'VIDEO.json');
const targetPath = join(OUTPUT_DIR, 'VIDEO.json');

try {
  copyFileSync(sourcePath, targetPath);
} catch (err) {
  fail(`VIDEO.json could not be copied from ${BOT_DIR}: ${(err as Error).message}`);
}

// Read-back self-check: verify what actually landed in /output.
let copied: Buffer;
try {
  copied = readFileSync(targetPath);
} catch (err) {
  fail(`VIDEO.json could not be read back from ${OUTPUT_DIR}: ${(err as Error).message}`);
}

const checks: Record<string, boolean> = {
  under_byte_cap: copied.length <= VIDEO_JSON_MAX_BYTES,
  parses_as_json: false,
  is_object: false,
  url_is_youtube_video: false,
  copy_matches_source: false,
};
let videoUrl = '';
let videoId = '';

// Copy-integrity check: the bytes that landed in /output must be exactly
// the bytes that left the repository — hash both sides and compare.
try {
  const source = readFileSync(sourcePath);
  checks.copy_matches_source =
    createHash('sha256').update(source).digest('hex') ===
    createHash('sha256').update(copied).digest('hex');
} catch {
  // copy_matches_source stays false; the dossier below records it.
}

try {
  const parsed: unknown = JSON.parse(copied.toString('utf8'));
  checks.parses_as_json = true;
  if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
    checks.is_object = true;
    const url = (parsed as Record<string, unknown>).url;
    if (typeof url === 'string') {
      videoUrl = url;
      const match = YOUTUBE_URL.exec(url);
      if (match) {
        checks.url_is_youtube_video = true;
        videoId = match[1];
      }
    }
  }
} catch {
  // parses_as_json stays false; the dossier below records the failure.
}

const passed = Object.values(checks).every(Boolean);

const dossier = {
  competition: COMPETITION,
  program: 'main.ts',
  video_url: videoUrl,
  video_id: videoId,
  video_json_bytes: copied.length,
  video_json_sha256: createHash('sha256').update(copied).digest('hex'),
  self_check: passed ? 'pass' : 'fail',
  checks,
  node: process.version,
};

try {
  writeFileSync(
    join(OUTPUT_DIR, 'dossier.json'),
    JSON.stringify(dossier, null, 2) + '\n',
    'utf8',
  );
} catch (err) {
  fail(`dossier.json could not be written to ${OUTPUT_DIR}: ${(err as Error).message}`);
}

if (!passed) {
  fail(`read-back self-check failed: ${JSON.stringify(checks)}`);
}

// Dossier round-trip: read back what was written and confirm it parses
// and records the same verdict this run computed.
try {
  const roundTrip: unknown = JSON.parse(
    readFileSync(join(OUTPUT_DIR, 'dossier.json'), 'utf8'),
  );
  if (
    roundTrip === null ||
    typeof roundTrip !== 'object' ||
    (roundTrip as Record<string, unknown>).self_check !== dossier.self_check ||
    (roundTrip as Record<string, unknown>).video_json_sha256 !==
      dossier.video_json_sha256
  ) {
    fail('dossier.json round-trip mismatch');
  }
} catch (err) {
  fail(`dossier.json could not be read back: ${(err as Error).message}`);
}
