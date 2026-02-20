// frontend/scripts/generate-types.ts
// Ejecutar con: npx tsx scripts/generate-types.ts
// O via: npm run generate-types

import openapiTS, { astToString } from "openapi-typescript";
import * as fs from "node:fs/promises";
import * as path from "node:path";
import * as url from "node:url";

const OPENAPI_URL = process.env["OPENAPI_URL"] ?? "http://localhost:8000/openapi.json";
const OUTPUT_PATH = path.resolve(
  path.dirname(url.fileURLToPath(import.meta.url)),
  "../src/types/generated/api.ts",
);

async function main(): Promise<void> {
  console.log(`Fetching OpenAPI spec from ${OPENAPI_URL}...`);

  const ast = await openapiTS(new URL(OPENAPI_URL));
  const content = astToString(ast);

  await fs.mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
  await fs.writeFile(
    OUTPUT_PATH,
    `// AUTO-GENERATED — DO NOT EDIT MANUALLY\n// Run: npm run generate-types\n// Source: ${OPENAPI_URL}\n\n${content}`,
  );

  console.log(`Types generated: ${OUTPUT_PATH}`);
}

main().catch((err: unknown) => {
  console.error("Type generation failed:", err);
  process.exit(1);
});
