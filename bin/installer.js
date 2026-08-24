#!/usr/bin/env node
// Provisions the skill into ~/.claude/ on install.
// Runs on `postinstall` for npm/pnpm/yarn/bun, and is also exposed as the
// `todo-audit-skill-install` bin for environments that disable install scripts.
//
// Two destinations, because Claude Code reads them from different places:
//   ~/.claude/skills/todo-audit-skill/   the SKILL.md and the Python engine
//   ~/.claude/commands/todo/             the slash commands -> /todo:audit etc.
// Commands nested inside a skill directory are NOT discovered, so they must be
// installed alongside it rather than within it.
import { execFileSync } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const pkgRoot = path.resolve(__dirname, '..');
const skillName = 'todo-audit-skill';
const claudeDir = path.join(os.homedir(), '.claude');
const skillDir = path.join(claudeDir, 'skills', skillName);
const commandDir = path.join(claudeDir, 'commands', 'todo');

const MIN_PYTHON = [3, 9];
const SKIP_ENTRIES = new Set(['__pycache__', '.pytest_cache', '.mypy_cache']);

// (sourceRelativeToPkgRoot -> absolute destination)
const assets = [
  ['skills/todo-audit-skill/SKILL.md', path.join(skillDir, 'SKILL.md')],
  ['src', path.join(skillDir, 'src')],
  ['commands', commandDir],
];

function isSkipped(entry) {
  return SKIP_ENTRIES.has(entry) || entry.endsWith('.pyc') || entry.endsWith('.egg-info');
}

function copyRecursive(src, dest) {
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    fs.mkdirSync(dest, { recursive: true });
    for (const entry of fs.readdirSync(src)) {
      if (isSkipped(entry)) continue;
      copyRecursive(path.join(src, entry), path.join(dest, entry));
    }
  } else {
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.copyFileSync(src, dest);
  }
}

// Replace rather than merge: a file dropped in a later release must not linger.
function replaceDir(dir, copy) {
  fs.rmSync(dir, { recursive: true, force: true });
  copy();
}

function checkPython() {
  for (const exe of ['python3', 'python']) {
    try {
      const out = execFileSync(exe, ['-c', 'import sys; print("%d.%d" % sys.version_info[:2])'], {
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'ignore'],
      }).trim();
      const [major, minor] = out.split('.').map(Number);
      if (major > MIN_PYTHON[0] || (major === MIN_PYTHON[0] && minor >= MIN_PYTHON[1])) {
        return { exe, version: out };
      }
      return { exe, version: out, tooOld: true };
    } catch {
      // try the next candidate
    }
  }
  return null;
}

try {
  replaceDir(skillDir, () => {
    fs.mkdirSync(skillDir, { recursive: true });
    for (const [rel, dest] of assets) {
      if (dest.startsWith(commandDir)) continue;
      const src = path.join(pkgRoot, rel);
      if (!fs.existsSync(src)) continue;
      copyRecursive(src, dest);
    }
  });

  replaceDir(commandDir, () => {
    const src = path.join(pkgRoot, 'commands');
    if (fs.existsSync(src)) copyRecursive(src, commandDir);
  });

  console.log(`✅ skill installed to ${skillDir}`);
  console.log(`✅ commands installed to ${commandDir} (/todo:audit, /todo:fix, /todo:analyze)`);

  const python = checkPython();
  if (!python) {
    console.warn('⚠️  no python3 found on PATH — the scanner cannot run until one is installed');
  } else if (python.tooOld) {
    console.warn(`⚠️  ${python.exe} is ${python.version}; the scanner needs Python ${MIN_PYTHON.join('.')}+`);
  } else {
    console.log(`✅ ${python.exe} ${python.version} detected`);
  }
} catch (error) {
  console.error('❌ Failed to install todo-audit-skill:', error.message);
  // Do not fail the whole `npm install` on a copy error.
  process.exit(0);
}
