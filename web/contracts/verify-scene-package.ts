import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

type JsonObject = Record<string, unknown>;

const repositoryRoot = fileURLToPath(new URL("../..", import.meta.url));

function readJson(relativePath: string): JsonObject {
  return JSON.parse(readFileSync(`${repositoryRoot}/${relativePath}`, "utf8")) as JsonObject;
}

const schema = readJson("contracts/scene-constraint-package.v1.schema.json");
const fixture = readJson("examples/scene-constraint-package.example.json");
const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
const validate = ajv.compile(schema);

assert.equal(validate(fixture), true, ajv.errorsText(validate.errors));

const unsafePath = structuredClone(fixture);
const unsafePasses = unsafePath.passes as Array<JsonObject>;
const unsafeArtifact = unsafePasses[0].artifact as JsonObject;
unsafeArtifact.path = "../outside.png";
assert.equal(validate(unsafePath), false, "package traversal must fail closed");

const duplicatePass = structuredClone(fixture);
const duplicatePasses = duplicatePass.passes as Array<JsonObject>;
duplicatePasses[3].kind = duplicatePasses[0].kind;
assert.equal(validate(duplicatePass), false, "duplicate required render pass must fail closed");

const missingPass = structuredClone(fixture);
const missingPasses = missingPass.passes as Array<JsonObject>;
missingPasses.pop();
assert.equal(validate(missingPass), false, "missing required render pass must fail closed");

process.stdout.write("TypeScript contract verification passed.\n");
