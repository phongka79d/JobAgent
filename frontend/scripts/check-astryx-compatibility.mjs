import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const expectedVersion = "0.1.4";
const publicExports = {
  AppShell: ["AppShell"],
  SideNav: ["SideNav", "SideNavHeading"],
  FileInput: ["FileInput"],
  StatusDot: ["StatusDot"],
  Token: ["Token"],
  Link: ["Link"],
  VStack: ["VStack"],
  HStack: ["HStack"],
  Text: ["Text"],
  Chat: [
    "ChatLayout",
    "ChatComposer",
    "ChatComposerDrawer",
    "ChatToolCalls",
    "ChatMessage",
    "ChatMessageList",
    "ChatSystemMessage",
  ],
  ButtonGroup: ["ButtonGroup"],
  Button: ["Button"],
  Card: ["Card"],
  Collapsible: ["Collapsible"],
  ProgressBar: ["ProgressBar"],
  MetadataList: ["MetadataList", "MetadataListItem"],
  Badge: ["Badge"],
  Banner: ["Banner"],
  Toast: ["Toast"],
};

const packageJson = JSON.parse(
  await readFile(new URL("../node_modules/@astryxdesign/core/package.json", import.meta.url)),
);

assert.equal(packageJson.version, expectedVersion, "Astryx core version must match the locked pin");

for (const [subpath, names] of Object.entries(publicExports)) {
  assert.ok(packageJson.exports[`./${subpath}`], `${subpath} must be a public package export`);

  const module = await import(`@astryxdesign/core/${subpath}`);
  for (const name of names) {
    assert.ok(name in module, `${name} must resolve from the public ${subpath} export`);
  }
}

const componentCount = Object.values(publicExports).reduce(
  (sum, names) => sum + names.length,
  0,
);
console.log(
  `PASS: Astryx ${expectedVersion} exposes all ${componentCount} required public components.`,
);
