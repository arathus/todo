#!/usr/bin/env node
// Provisions the skill into ~/.claude/skills/todo-audit-skill/ on install.
// Runs on `postinstall` for npm/pnpm/yarn/bun, and is also exposed as the
// `todo-audit-skill-install` bin for environments that disable install scripts.
import fs from 'fs';
import path from 'path';
import os from 'os';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pkgRoot = path.resolve(__dirname, '..');
const skillName = 'todo-audit-skill';
const targetDir = path.join(os.homedir(), '.claude', 'skills', skillName);

// (sourceRelativeToPkgRoot -> destinationRelativeToTargetDir)
const assets = [
  ['skills/todo-audit-skill/SKILL.md', 'SKILL.md'],
  ['src', 'src'],
  ['commands', 'commands'],
];

function copyRecursive(src, dest) {
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(src)) {
      if (entry === '__pycache__' || entry.endsWith('.pyc')) continue;
      copyRecursive(path.join(src, entry), path.join(dest, entry));
    }
  } else {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(src, dest);
  }
}

try {
  fs.mkdirSync(targetDir, { recursive: true });
  for (const [rel, destRel] of assets) {
    const src = path.join(pkgRoot, rel);
    if (!fs.existsSync(src)) continue;
    copyRecursive(src, path.join(targetDir, destRel));
  }
  console.log(`✅ todo-audit-skill installed to ${targetDir}`);
} catch (error) {
  console.error('❌ Failed to install todo-audit-skill:', error.message);
  // Do not fail the whole `npm install` on a copy error.
  process.exit(0);
}
