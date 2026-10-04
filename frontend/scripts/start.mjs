import { cp, access } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const standalone = path.join(root, ".next/standalone");
try {
  await access(path.join(standalone, "server.js"));
} catch {
  console.error("Run npm run build before npm start.");
  process.exit(1);
}
await cp(path.join(root, ".next/static"), path.join(standalone, ".next/static"), { recursive: true });
try {
  await access(path.join(root, "public"));
  await cp(path.join(root, "public"), path.join(standalone, "public"), { recursive: true });
} catch { /* This app currently has no public asset directory. */ }
const child = spawn(process.execPath, [path.join(standalone, "server.js")], {
  cwd: standalone, stdio: "inherit",
  env: { ...process.env, HOSTNAME: process.env.HOSTNAME || "127.0.0.1", PORT: process.env.PORT || "3000" },
});
child.on("exit", code => process.exit(code ?? 0));
child.on("error", error => { console.error(error.message); process.exit(1); });
process.on("SIGINT", () => child.kill());
process.on("SIGTERM", () => child.kill());
